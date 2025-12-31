#!/usr/bin/env python3

import sys
import json
import re
from datetime import datetime
from urllib.parse import urlparse
import os

import requests
import urllib3

try:
    import config  # type: ignore
except ImportError as exc:
    raise SystemExit(
        "Configuração não encontrada. Certifique-se de que o arquivo 'config.py' exista no mesmo diretório."
    ) from exc

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ======================= CONFIG ZABBIX =======================
# As constantes relativas ao Zabbix são obtidas do arquivo de configuração.
ZABBIX_API_URL = config.ZABBIX_API_URL
ZABBIX_API_TOKEN = config.ZABBIX_API_TOKEN
ZABBIX_VERIFY_SSL = config.ZABBIX_VERIFY_SSL


def _log_ticket_action(action: str, ticket_number: str, id_atividade: str = "", nome_atividade: str = "") -> None:
    """
    Log simples de abertura/fechamento de ticket.

    Formato (uma linha):
      YYYY-MM-DD HH:MM:SS ACTION ticket=<N>

    OBS: arquivo padrão 'tickets.log' no mesmo diretório do script.
    Pode ser sobrescrito por variável de ambiente: CITSMART_LOG_FILE
    """
    log_file = os.environ.get("CITSMART_LOG_FILE") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "tickets.log"
    )
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} {action.upper()} ticket={ticket_number}\n"
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        # log nunca deve quebrar o fluxo principal
        pass


def zabbix_api(method: str, params: dict):
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ZABBIX_API_TOKEN}"}
    try:
        r = requests.post(
            ZABBIX_API_URL,
            json=payload,
            headers=headers,
            verify=ZABBIX_VERIFY_SSL,
            timeout=(10, 60),
        )
        data = r.json()
    except Exception as e:
        return None

    if isinstance(data, dict) and "error" in data:
        return None

    return data.get("result") if isinstance(data, dict) else None


def zabbix_ack_problem_event(problem_event_id: str, message: str) -> bool:
    # action=6 => 2 (acknowledge) + 4 (add message)
    res = zabbix_api(
        "event.acknowledge",
        {"eventids": str(problem_event_id), "action": 6, "message": message},
    )
    return bool(res)


TICKET_RE = re.compile(r"CITSmartTicketID\s*=\s*(\d+)")


def extract_ticket_from_acks(event_obj: dict) -> str | None:
    acks = event_obj.get("acknowledges") or []
    for ack in acks:
        msg = ack.get("message") or ""
        m = TICKET_RE.search(msg)
        if m:
            return m.group(1)
    return None


def get_event_with_acks(event_id: str) -> dict | None:
    res = zabbix_api(
        "event.get",
        {
            "eventids": [str(event_id)],
            "output": ["eventid", "objectid", "value", "clock"],
            "select_acknowledges": ["message", "clock"],
        },
    )
    if not res:
        return None
    if isinstance(res, list) and res:
        return res[0]
    return None


def get_latest_problem_event_for_trigger(trigger_id: str) -> dict | None:
    # Busca eventos de problema (value=1) do trigger e pega o mais recente.
    res = zabbix_api(
        "event.get",
        {
            "object": 0,  # 0 = trigger events
            "source": 0,  # 0 = triggers
            "objectids": [str(trigger_id)],
            "value": 1,
            "output": ["eventid", "objectid", "value", "clock"],
            "select_acknowledges": ["message", "clock"],
            "sortfield": ["clock"],
            "sortorder": "DESC",
            "limit": 20,
        },
    )
    if not res or not isinstance(res, list):
        return None

    # Normalmente o primeiro já é o último problema; mas varremos até achar ticket no ack.
    for ev in res:
        if extract_ticket_from_acks(ev):
            return ev

    # Se nenhum tiver ticket, ainda retornamos o mais recente para facilitar debug.
    return res[0] if res else None


def find_ticket_for_zabbix_event(event_id: str) -> tuple[str | None, str | None]:
    """Retorna (ticket_id, problem_event_id).

    1) tenta achar ticket no próprio event_id
    2) se não achar, trata event_id como recovery: pega trigger (objectid) e busca
       último event de problema do trigger.
    """
    ev = get_event_with_acks(event_id)
    if not ev:
        return None, None

    # Se for evento de problema e já tiver ack com ticket
    t = extract_ticket_from_acks(ev)
    if t:
        return t, str(ev.get("eventid"))

    # Caso comum: estamos no recovery. Descobre triggerid via objectid.
    trigger_id = ev.get("objectid")
    if not trigger_id:
        return None, None

    last_problem = get_latest_problem_event_for_trigger(str(trigger_id))
    if not last_problem:
        return None, None

    t2 = extract_ticket_from_acks(last_problem)
    return t2, str(last_problem.get("eventid")) if last_problem else None

class CITSmarTCloser:
    def __init__(
        self,
        base_url: str = config.CITSMART_BASE_URL,
        forced_host: str = config.CITSMART_FORCED_HOST,
        user: str = config.CITSMART_USER,
        password: str = config.CITSMART_PASSWORD,
        platform: str = config.CITSMART_PLATFORM,
        timeout_connect: int = 10,
        timeout_read: int = 60,
        debug: bool = False,
    ):
        self.base_url = self._normalize_base(base_url)
        self.forced_host = forced_host
        self.user = user
        self.password = password
        self.platform = platform
        self.timeout = (timeout_connect, timeout_read)
        self.debug = debug

        self.session = requests.Session()
        self.session.verify = False

        self.real_url = "/citsmart/serviceRequestIncident/serviceRequestIncident.load"

        self.login_path = "/citsmart/services/login"
        self.ep_restore = "/citsmart/rest/citajax/ticket/serviceRequestIncident/restoreRequest"
        self.ep_groups = "/citsmart/rest/citajax/ticket/serviceRequestIncident/groupsForCapture"
        self.ep_capture = "/citsmart/rest/citajax/ticket/serviceRequestIncident/capturarTarefa"
        self.ep_validate = "/citsmart/rest/citajax/ticket/serviceRequestIncident/validateConcurrentAccess"
        self.ep_save = "/citsmart/rest/citajax/ticket/serviceRequestIncident/saveOrUpdate"

        self.headers = self._build_headers()

    def _normalize_base(self, base: str) -> str:
        base = (base or "").strip().rstrip("/")
        if not base:
            base = config.CITSMART_BASE_URL
        if "://" not in base:
            base = "https://" + base
        return base.rstrip("/")

    def _build_headers(self) -> dict:
        if self.forced_host:
            origin = f"https://{self.forced_host}"
            referer = f"https://{self.forced_host}/"
        else:
            p = urlparse(self.base_url)
            origin = f"{p.scheme}://{p.netloc}"
            referer = origin + "/"

        h = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": origin,
            "Referer": referer,
        }
        if self.forced_host:
            h["Host"] = self.forced_host
        return h

    def _post(self, path: str, payload: dict, headers: dict | None = None):
        url = self.base_url + path
        h = headers or self.headers
        r = self.session.post(url, json=payload, headers=h, timeout=self.timeout)
        return r

    def _now_dt(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _die(self, msg: str, code: int = 2):
        print(f"❌ {msg}", file=sys.stderr)
        sys.exit(code)

    def login(self) -> bool:
        print("Realizando login no CITSmart...")
        url = self.base_url + self.login_path
        payload = {"userName": self.user, "password": self.password, "platform": self.platform}

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.forced_host:
            headers["Host"] = self.forced_host

        r = self.session.post(url, json=payload, headers=headers, timeout=self.timeout)
        return r.status_code == 200

    def restore_request(self, ticket_id: int, view: bool = False) -> dict:
        payload = {"object": {"idSolicitacaoServico": int(ticket_id), "view": bool(view)}, "realUrl": self.real_url}
        r = self._post(self.ep_restore, payload)
        if r.status_code != 200:
            self._die(f"restoreRequest falhou (HTTP {r.status_code}).")
        try:
            dto = r.json()
        except Exception:
            self._die("restoreRequest não retornou JSON.")
        if not isinstance(dto, dict) or "id" not in dto:
            self._die("restoreRequest retornou JSON inesperado (não parece DTO de ticket).")
        return dto

    def groups_for_capture(self, id_item_trabalho: int):
        payload = {"object": {"idItemTrabalho": int(id_item_trabalho)}, "realUrl": self.real_url}
        r = self._post(self.ep_groups, payload)
        if r.status_code != 200:
            self._die(f"groupsForCapture falhou (HTTP {r.status_code}).")
        return r

    def capturar_tarefa(self, dto: dict):
        payload = {"object": dto, "realUrl": self.real_url}
        r = self._post(self.ep_capture, payload)
        if r.status_code != 200:
            self._die(f"capturarTarefa falhou (HTTP {r.status_code}).")
        try:
            return r.json()
        except Exception:
            return {}

    def validate_concurrent_access(self, ticket_id: int, id_item_trabalho: int, id_usuario_responsavel_atual: int | None, dt_last_mod: str):
        obj = {"id": int(ticket_id), "idItemTrabalho": int(id_item_trabalho), "dtLastModification": dt_last_mod}
        if id_usuario_responsavel_atual is not None:
            obj["idUsuarioResponsavelAtual"] = int(id_usuario_responsavel_atual)
        payload = {"object": obj, "realUrl": self.real_url}
        r = self._post(self.ep_validate, payload)
        if r.status_code != 200:
            return None
        try:
            return r.json()
        except Exception:
            return None

    def save_or_update(self, dto: dict):
        payload = {"object": dto, "realUrl": self.real_url}
        r = self._post(self.ep_save, payload)
        if r.status_code != 200:
            self._die(f"saveOrUpdate falhou (HTTP {r.status_code}).", 1)
        return r

    def aplicar_resolucao(self, dto: dict, status_id: int, acao_fluxo: str, id_categoria_solucao: int, id_causa_incidente: int, solucao_html: str, causa_html: str):
        dto["idStatus"] = int(status_id)
        dto["acaoFluxo"] = str(acao_fluxo)
        dto["idCategoriaSolucao"] = int(id_categoria_solucao)
        dto["idCausaIncidente"] = int(id_causa_incidente)
        dto["solucaoResposta"] = solucao_html
        dto["detalhamentoCausa"] = causa_html
        dto["view"] = False
        dto["commentMode"] = False
        dto["dtLastModification"] = self._now_dt()
        return dto

    def executar_fluxo_fechamento(
        self,
        ticket_id: int,
        id_item_trabalho: int | None,
        status_id: int = 4,
        acao_fluxo: str = "E",
        id_categoria_solucao: int = 13,
        id_causa_incidente: int = 6,
        solucao_html: str = "<div>Resolvido automaticamente via Zabbix (OK).</div>",
        causa_html: str = "<div>Recuperação detectada pelo Zabbix.</div>",
    ):
        print("Iniciando fechamento (fluxo completo)...")

        if not self.login():
            self._die("Falha no login.", 2)

        dto1 = self.restore_request(ticket_id, view=False)

        if id_item_trabalho is None:
            id_item_trabalho = dto1.get("idItemTrabalho")
            if not id_item_trabalho:
                self._die("Não consegui descobrir idItemTrabalho via restoreRequest.", 2)

        dto1["id"] = int(ticket_id)
        dto1["idItemTrabalho"] = int(id_item_trabalho)

        self.groups_for_capture(id_item_trabalho)
        cap = self.capturar_tarefa(dto1)

        dt_cap = cap.get("dtLastModification") or dto1.get("dtLastModification") or self._now_dt()
        id_usr = dto1.get("idUsuarioResponsavelAtual")

        self.validate_concurrent_access(ticket_id, id_item_trabalho, id_usr, dt_cap)

        dto1 = self.aplicar_resolucao(dto1, status_id, acao_fluxo, id_categoria_solucao, id_causa_incidente, solucao_html, causa_html)
        dto1.setdefault("original", {})

        self.save_or_update(dto1)
        print("✅ 1º saveOrUpdate OK")

        dto2 = self.restore_request(ticket_id, view=False)
        id_item_2 = dto2.get("idItemTrabalho") or id_item_trabalho
        dto2["id"] = int(ticket_id)
        dto2["idItemTrabalho"] = int(id_item_2)

        dto2 = self.aplicar_resolucao(dto2, status_id, acao_fluxo, id_categoria_solucao, id_causa_incidente, solucao_html, causa_html)
        dto2.setdefault("original", {})

        self.save_or_update(dto2)
        print("✅ 2º saveOrUpdate OK")
        print("✅ Fechamento finalizado.")

        # LOG de fechamento do ticket (tenta puxar descrição via restoreRequest)
        try:
            id_atv = str(dto2.get("idAtividade") or dto1.get("idAtividade") or getattr(config, "ID_ATIVIDADE", "") or "")
            nome_atv = str(dto2.get("nomeAtividade") or dto2.get("dsAtividade") or dto1.get("nomeAtividade") or dto1.get("dsAtividade") or "")
            _log_ticket_action("CLOSE", str(ticket_id), id_atv, nome_atv)
        except Exception:
            pass


def main():
    if len(sys.argv) < 2:
        print("Uso:")
        print("  python3 close.py token")
        print("  python3 close.py fluxo <ticket_id> [solucao_html] [causa_html] [--debug] [--id-item-trabalho X]")
        print("  python3 close.py zabbix <event_id> [solucao_html] [causa_html]")
        sys.exit(1)

    cmd = sys.argv[1].lower()

    # Defaults fixos baseados no arquivo de configuração
    base = config.CITSMART_BASE_URL
    host = config.CITSMART_FORCED_HOST
    user = config.CITSMART_USER
    pwd = config.CITSMART_PASSWORD
    platform = config.CITSMART_PLATFORM

    debug = ("--debug" in sys.argv) or ("--print-response" in sys.argv)

    def _get_flag_value(flag: str):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                return sys.argv[i + 1]
        return None

    id_item_trabalho = _get_flag_value("--id-item-trabalho")
    if id_item_trabalho is not None:
        try:
            id_item_trabalho = int(id_item_trabalho)
        except ValueError:
            print("❌ --id-item-trabalho precisa ser inteiro")
            sys.exit(2)

    status_id = _get_flag_value("--status-id")
    acao_fluxo = _get_flag_value("--acao-fluxo")
    id_cat = _get_flag_value("--id-categoria-solucao")
    id_causa = _get_flag_value("--id-causa-incidente")

    timeout_connect = _get_flag_value("--timeout-connect")
    timeout_read = _get_flag_value("--timeout-read")

    closer = CITSmarTCloser(
        base_url=base,
        forced_host=host,
        user=user,
        password=pwd,
        platform=platform,
        timeout_connect=int(timeout_connect) if timeout_connect else 10,
        timeout_read=int(timeout_read) if timeout_read else 60,
        debug=debug,
    )

    if cmd == "token":
        ok = closer.login()
        print("✅ Login OK" if ok else "❌ Login falhou")
        return

    if cmd == "fluxo":
        if len(sys.argv) < 3:
            print("Uso: python3 close.py fluxo <ticket_id> [solucao_html] [causa_html] ...")
            sys.exit(1)

        try:
            ticket_id = int(sys.argv[2])
        except ValueError:
            print("❌ ticket_id precisa ser inteiro")
            sys.exit(2)

        solucao_html = "<div>Resolvido automaticamente via Zabbix (OK).</div>"
        causa_html = "<div>Recuperação detectada pelo Zabbix.</div>"

        if len(sys.argv) >= 4 and not sys.argv[3].startswith("--"):
            solucao_html = sys.argv[3]
        if len(sys.argv) >= 5 and not sys.argv[4].startswith("--"):
            causa_html = sys.argv[4]

        closer.executar_fluxo_fechamento(
            ticket_id=ticket_id,
            id_item_trabalho=id_item_trabalho,
            status_id=int(status_id) if status_id else 4,
            acao_fluxo=str(acao_fluxo) if acao_fluxo else "E",
            id_categoria_solucao=int(id_cat) if id_cat else 13,
            id_causa_incidente=int(id_causa) if id_causa else 6,
            solucao_html=solucao_html,
            causa_html=causa_html,
        )
        return

    if cmd == "zabbix":
        if len(sys.argv) < 3:
            print("Uso: python3 close.py zabbix <event_id> [solucao_html] [causa_html]")
            sys.exit(1)

        event_id = str(sys.argv[2]).strip()

        solucao_html = "<div>Problema resolvido automaticamente pelo Zabbix</div>"
        causa_html = "<div>Trigger voltou ao estado OK</div>"

        if len(sys.argv) >= 4 and not sys.argv[3].startswith("--"):
            solucao_html = sys.argv[3]
        if len(sys.argv) >= 5 and not sys.argv[4].startswith("--"):
            causa_html = sys.argv[4]

        ticket_id, problem_event_id = find_ticket_for_zabbix_event(event_id)
        if not ticket_id:
            print("❌ Não foi possível localizar o número do ticket no evento relacionado.")
            sys.exit(2)

        closer.executar_fluxo_fechamento(
            ticket_id=int(ticket_id),
            id_item_trabalho=id_item_trabalho,
            status_id=int(status_id) if status_id else 4,
            acao_fluxo=str(acao_fluxo) if acao_fluxo else "E",
            id_categoria_solucao=int(id_cat) if id_cat else 13,
            id_causa_incidente=int(id_causa) if id_causa else 6,
            solucao_html=solucao_html,
            causa_html=causa_html,
        )

        # Opcional: escreve um ack no evento de PROBLEMA (é nele que o Zabbix permite event.acknowledge).
        if problem_event_id:
            zabbix_ack_problem_event(problem_event_id, f"CITSmartTicketClosed={ticket_id}")

        print(f"✅ Fechamento OK (ticket {ticket_id})")
        return

    print("Comandos disponíveis:")
    print("  token   - apenas login")
    print("  fluxo   - fecha/resolve ticket (CITSmart)")
    print("  zabbix  - fecha automaticamente via evento do Zabbix")
    sys.exit(1)

if __name__ == "__main__":
    main()
