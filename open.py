#!/usr/bin/env python3

import requests
import sys
import urllib.parse
from datetime import datetime
import json
import re
import urllib3
import os

try:
    import config  # type: ignore
except ImportError as exc:
    raise SystemExit(
        "Configuração não encontrada. Certifique-se de que o arquivo 'config.py' exista no mesmo diretório."
    ) from exc

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
    """
    Executa uma chamada à API JSON-RPC do Zabbix.

    :param method: Nome do método da API (por exemplo, 'event.acknowledge').
    :param params: Dicionário com os parâmetros do método.
    :return: Resultado retornado pelo Zabbix ou None em caso de erro.
    """
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1,
        "auth": ZABBIX_API_TOKEN,
    }
    try:
        response = requests.post(
            ZABBIX_API_URL, json=payload, verify=ZABBIX_VERIFY_SSL
        )
        response.raise_for_status()
        data = response.json()
        # Verifica se houve erro
        if isinstance(data, dict) and data.get("error"):
            print(f"Erro na API do Zabbix: {data['error']}")
            return None
        return data.get("result")
    except Exception as exc:
        print(f"Erro ao chamar API do Zabbix: {exc}")
        return None


def zabbix_acknowledge(event_id: str, ticket_number: str, observacao: str = ""):
    """
    Reconhece um evento no Zabbix adicionando uma mensagem com o número do ticket
    do CITSmart. O parâmetro `action` usa valor 6 (2 + 4) para ao mesmo tempo
    reconhecer o evento e anexar uma mensagem.

    :param event_id: ID do evento Zabbix a ser reconhecido.
    :param ticket_number: Número do ticket criado no CITSmart.
    :param observacao: Texto adicional para descrever o chamado.
    :return: Resultado da chamada à API do Zabbix ou None.
    """
    mensagem = f"CITSmartTicketID={ticket_number}"
    if observacao:
        # separa com pipe para facilitar a leitura
        mensagem += f" | {observacao}"
    params = {
        "eventids": [str(event_id)],
        # 6 = 2 (acknowledge event) + 4 (add message)
        "action": 6,
        "message": mensagem,
    }
    return zabbix_api("event.acknowledge", params)

# Suprimir avisos SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class CITSmarTAutomation:
    def __init__(self, base_url: str = config.CITSMART_BASE_URL):
        """
        Inicializa a automação CITSmart.

        :param base_url: Endereço base do CITSmart. Por padrão, utiliza
                          o valor definido em config.CITSMART_BASE_URL.
        """
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        # Aceitar ou não certificado SSL é configurado no objeto session;
        # manter False se o certificado for autoassinado.
        self.session.verify = False

    def login(self):
        """Realiza login no sistema e obtém cookies"""
        print("Realizando login no sistema CITSmarT...")

        login_url = f"{self.base_url}/citsmart/services/login"
        login_data = {
            "userName": config.CITSMART_USER,
            "password": config.CITSMART_PASSWORD,
            "platform": config.CITSMART_PLATFORM,
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            response = self.session.post(
                login_url,
                json=login_data,
                headers=headers,
            )

            if response.status_code == 200:
                print("Login realizado com sucesso!")
                return True
            else:
                print(f"Erro no login. Status code: {response.status_code}")
                return False

        except Exception as e:
            print(f"Erro durante o login: {e}")
            return False

    def _get_ticket_activity_info(self, ticket_number: str) -> tuple[str, str]:
        """
        Tenta buscar do próprio CITSmart (restoreRequest) a atividade relacionada ao ticket,
        retornando (idAtividade, nomeAtividade). Caso não encontre, retorna valores de fallback.
        """
        # Fallback (mantém seu comportamento atual)
        fallback_id = str(getattr(config, "ID_ATIVIDADE", "") or "")
        fallback_nome = "Erro no Solicita"

        try:
            url_restore = f"{self.base_url}/citsmart/rest/citajax/ticket/serviceRequestIncident/restoreRequest"
            payload_restore = {
                "object": {"idSolicitacaoServico": int(ticket_number)},
                "realUrl": "/citsmart/serviceRequestIncident/serviceRequestIncident.load",
            }
            headers_restore = {"Content-Type": "application/json", "Accept": "application/json"}
            rrestore = self.session.post(url_restore, json=payload_restore, headers=headers_restore)
            if rrestore.status_code != 200:
                return fallback_id, fallback_nome
            dto = rrestore.json() if rrestore.content else {}
            if not isinstance(dto, dict):
                return fallback_id, fallback_nome

            id_atividade = str(dto.get("idAtividade") or dto.get("id_atividade") or dto.get("idActivity") or fallback_id)
            nome_atividade = str(dto.get("nomeAtividade") or dto.get("dsAtividade") or dto.get("atividade") or fallback_nome)

            # Se vier vazio, usa fallback
            if not id_atividade:
                id_atividade = fallback_id
            if not nome_atividade:
                nome_atividade = fallback_nome

            return id_atividade, nome_atividade
        except Exception:
            return fallback_id, fallback_nome

    def adicionar_solicitacao_servico(self, observacao="teste"):
        """Adiciona uma solicitação de serviço"""
        print("Adicionando solicitação de serviço...")
        print(f"Descrição do chamado: {observacao}")

        url = f"{self.base_url}/citsmart/pages/smartPortal/smartPortal.event"

        data = {
            "uuid": "4149ce29-154f2bfa-cdb2d33b-b13493cb",
            "idPortfolio": "1",
            "idServico": "1494",
            "idAtividade": config.ID_ATIVIDADE,
            "nomeAtividade": "Erro no Solicita",
            "mostrarDescPortal": "S",
            "idQuestionario": "",
            "questionarioObrigatorio": "false",
            "questionarioRespondido": "false",
            "requestStatus": "",
            "idManager": "0",
            "serializedBuilderObjects": "{}",
            "idsItemConfiguracaoSelecionados": "",
            "idContrato": "2",
            "requestTitle": "",
            "solicitacaoObservacao": observacao,
            "nomeDoManager": "",
            "method": "execute",
            "parmCount": "",
            "parm1": "smartPortal",
            "parm2": "",
            "parm3": "adicionaSolicitacaoServico",
            "nocache": datetime.now().strftime(
                "%a %b %d %Y %H:%M:%S GMT-0300 (Horário Padrão de Brasília)"
            ),
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{self.base_url}/citsmart/pages/smartPortal/smartPortal.load",
        }

        try:
            response = self.session.post(url, data=data, headers=headers)
            return response
        except Exception as e:
            print(f"Erro ao adicionar solicitação: {e}")
            return None

    def salvar_meus_pedidos(self):
        """Salva os pedidos e retorna o número do ticket"""
        print("Salvando meus pedidos...")

        url = f"{self.base_url}/citsmart/pages/smartPortal/smartPortal.event"

        data = {
            "uuid": "",
            "requestStatus": "",
            "requestMessage": "",
            "removeLastTicketWhenErrorOccurs": "true",
            "method": "execute",
            "parmCount": "",
            "parm1": "smartPortal",
            "parm2": "",
            "parm3": "saveMeusPedidos",
            "nocache": datetime.now().strftime(
                "%a %b %d %Y %H:%M:%S GMT-0300 (Horário Padrão de Brasília)"
            ),
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{self.base_url}/citsmart/pages/smartPortal/smartPortal.load",
        }

        try:
            response = self.session.post(url, data=data, headers=headers)

            # Tentar extrair o número do ticket da resposta
            if response.status_code == 200:
                try:
                    # Tentar parsear como JSON primeiro
                    response_data = response.json()

                    # Procurar por campos que podem conter o número do ticket
                    ticket_number = None
                    if "ticketNumber" in response_data:
                        ticket_number = response_data["ticketNumber"]
                    elif "ticket" in response_data:
                        ticket_number = response_data["ticket"]
                    elif "number" in response_data:
                        ticket_number = response_data["number"]
                    elif "id" in response_data:
                        ticket_number = response_data["id"]

                    if ticket_number:
                        return response, ticket_number
                    else:
                        return response, None

                except json.JSONDecodeError:
                    # Se não for JSON, tentar extrair de texto
                    response_text = response.text

                    # Padrões comuns para números de ticket
                    patterns = [
                        r"class=\\#33#text-citsmart\\#33#\s*>\s*(\d+)\s*</h[23]>",
                        # Padrão específico do CITSmarT
                        r"<h2[^>]*class=\"[^\"]*text-citsmart[^\"]*\"[^>]*>\s*(\d+)\s*</h2>",
                        # Padrão HTML mais genérico
                        r"<span[^>]*class=\"[^\"]*label-numero[^\"]*\"[^>]*>Ticket</span><h2[^>]*class=\"[^\"]*text-citsmart[^\"]*\"[^>]*>\s*(\d+)\s*</h[23]>",
                        # Padrão completo
                        r"ticket[:\s]*(\d+)",
                        r"ticketNumber[:\s]*(\d+)",
                        r"number[:\s]*(\d+)",
                        r"id[:\s]*(\d+)",
                        r"(\d{5,})",  # Números com 5+ dígitos (ajustado para capturar 52606)
                    ]

                    for pattern in patterns:
                        match = re.search(pattern, response_text, re.IGNORECASE)
                        if match:
                            ticket_number = match.group(1)
                            return response, ticket_number

                    return response, None

            return response, None

        except Exception as e:
            print(f"Erro ao salvar pedidos: {e}")
            return None, None

    def abrir_atividade(self):
        """Abre uma atividade"""
        print("Abrindo atividade...")

        url = f"{self.base_url}/citsmart/pages/smartPortal/smartPortal.event"

        data = {
            "idPortfolio": "1",
            "idServico": "1494",
            "idAtividade": config.ID_ATIVIDADE,
            "tipoPortfolio": "",
            "nomePortfolio": "Central",
            "nomeServicoNegocio": "Solicita",
            "nomeAtividade": "Erro no Solicita",
            "servicosAdicionados": "",
            "method": "execute",
            "parmCount": "",
            "parm1": "smartPortal",
            "parm2": "",
            "parm3": "openAtividade",
            "nocache": datetime.now().strftime(
                "%a %b %d %Y %H:%M:%S GMT-0300 (Horário Padrão de Brasília)"
            ),
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{self.base_url}/citsmart/pages/smartPortal/smartPortal.load",
        }

        try:
            response = self.session.post(url, data=data, headers=headers)
            return response
        except Exception as e:
            print(f"Erro ao abrir atividade: {e}")
            return None

    def delegar_tarefa(self, ticket_number: str, observacao: str = "", id_grupo_destino: str = config.ID_GRUPO_DESTINO):
        """
        Delegar a tarefa recém-criada para um grupo específico.

        O CITSmart permite delegar a tarefa de um chamado a um grupo de atendimento
        logo após sua criação. Este método envia uma requisição semelhante à
        que é gerada ao clicar no botão "Delegar" na interface web. Por
        simplicidade, tentamos descobrir o `idTarefa` a partir do HTML
        retornado pela abertura da atividade; caso não seja possível, enviamos
        a requisição sem esse parâmetro (algumas instalações podem aceitá-lo
        em branco).

        :param ticket_number: Número do ticket (idSolicitacaoServico).
        :param observacao: Texto de justificativa da delegação.
        :param id_grupo_destino: ID do grupo de destino (padrão: "71").
        :return: Objeto Response ou None em caso de erro.
        """
        print("Delegando tarefa para o grupo", id_grupo_destino)
        # Primeiro, tentar obter o idTarefa e o id interno da solicitação via restoreRequest
        id_tarefa = ""
        id_solicitacao_servico = ticket_number
        try:
            # Utiliza o endpoint REST citajax, semelhante ao usado no close.py, para obter dados da solicitação
            url_restore = f"{self.base_url}/citsmart/rest/citajax/ticket/serviceRequestIncident/restoreRequest"
            payload_restore = {
                "object": {"idSolicitacaoServico": int(ticket_number)},
                "realUrl": "/citsmart/serviceRequestIncident/serviceRequestIncident.load",
            }
            headers_restore = {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            rrestore = self.session.post(
                url_restore, json=payload_restore, headers=headers_restore
            )
            if rrestore.status_code == 200:
                try:
                    dto = rrestore.json()
                    # idItemTrabalho geralmente corresponde ao idTarefa para delegação
                    id_tarefa = str(dto.get("idItemTrabalho", ""))
                    # Alguns retornam idSolicitacaoServico ou id, usamos para delegação se disponível
                    id_solicitacao_servico = str(
                        dto.get("idSolicitacaoServico") or dto.get("id") or ticket_number
                    )
                except Exception:
                    pass
        except Exception:
            # falha ao chamar restoreRequest, prossegue com ticket_number e sem id_tarefa
            pass
        # Se não conseguiu via restoreRequest, tenta extrair idTarefa da página de atividade
        if not id_tarefa:
            try:
                resp = self.abrir_atividade()
                if resp and resp.status_code == 200:
                    texto = resp.text
                    patterns = [
                        r'name="idTarefa"\s*value="(\d+)"',
                        r'"idTarefa"\s*:\s*"?(\d+)"?',
                        r'idTarefa=(\d+)',
                    ]
                    for pat in patterns:
                        m = re.search(pat, texto)
                        if m:
                            id_tarefa = m.group(1)
                            break
            except Exception:
                pass

        url = f"{self.base_url}/citsmart/pages/smartPortal/delegacaoTarefa.save"
        # Monta dados para delegação, conforme inspeção da chamada web (payload de delegação)
        data = {
            'idSolicitacaoServico': id_solicitacao_servico,
            'idTarefa': id_tarefa,
            'acaoFluxo': 'D',
            'idUsuarioDestino': '',
            'txtFiltro': '',
            'acUsuario': '',
            'idGrupoDestino': str(id_grupo_destino),
            'delegacaoJustificativa': observacao or 'Delegado automaticamente via integração',
            'nocache': datetime.now().strftime('%a %b %d %Y %H:%M:%S GMT-0300 (Horário Padrão de Brasília)'),
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': f'{self.base_url}/citsmart/pages/smartPortal/smartPortal.load',
        }
        try:
            response = self.session.post(url, data=data, headers=headers)
            if response.status_code == 200:
                print("Delegação efetuada com sucesso!")
            else:
                print(f"Falha ao delegar tarefa. Status: {response.status_code}")
            return response
        except Exception as e:
            print(f"Erro ao delegar tarefa: {e}")
            return None

    def executar_fluxo_completo(self, observacao="teste"):
        """Executa o fluxo completo de automação"""
        print("Iniciando fluxo completo de automação...")

        # 1. Login
        if not self.login():
            print("Falha no login. Abortando execução.")
            return False

        # 2. Adicionar solicitação de serviço
        response1 = self.adicionar_solicitacao_servico(observacao)
        if response1 and response1.status_code == 200:
            print("Solicitação de serviço adicionada com sucesso!")
        else:
            print("Falha ao adicionar solicitação de serviço.")

        # 3. Salvar meus pedidos
        response2, ticket_number = self.salvar_meus_pedidos()
        if response2 and response2.status_code == 200:
            print("Pedidos salvos com sucesso!")
            if ticket_number:
                print(f"✅ Ticket criado com sucesso! Número: {ticket_number}")
                # LOG de abertura do ticket (puxando descrição via CITSmart, se possível)
                id_atv, nome_atv = self._get_ticket_activity_info(str(ticket_number))
                _log_ticket_action("OPEN", str(ticket_number), id_atv, nome_atv)
            else:
                print("⚠️ Ticket criado, mas não foi possível obter o número")
        else:
            print("Falha ao salvar pedidos.")

        # 4. Abrir atividade
        response3 = self.abrir_atividade()
        if response3 and response3.status_code == 200:
            print("Atividade aberta com sucesso!")
            # 5. Delegar a tarefa para o grupo padrão (71) se houver ticket
            if ticket_number:
                # Usa a observação como justificativa da delegação (ou uma mensagem genérica)
                self.delegar_tarefa(ticket_number, observacao=observacao)
        else:
            print("Falha ao abrir atividade.")

        print("Fluxo completo finalizado!")
        return True


def main():
        """Função principal"""
        if len(sys.argv) > 1:
            comando = sys.argv[1]

            automation = CITSmarTAutomation()

            # Obter observação se fornecida
            observacao = "teste"  # valor padrão
            if len(sys.argv) > 2:
                observacao = sys.argv[2]

            if comando == "token":
                # Apenas login
                automation.login()
            elif comando == "fluxo":
                # Executa o fluxo completo
                automation.executar_fluxo_completo(observacao)
            elif comando == "adicionar":
                # Apenas adicionar solicitação
                if automation.login():
                    automation.adicionar_solicitacao_servico(observacao)
            elif comando == "salvar":
                # Apenas salvar pedidos
                if automation.login():
                    response, ticket_number = automation.salvar_meus_pedidos()
                    if response and response.status_code == 200:
                        if ticket_number:
                            print(f"✅ Ticket criado com sucesso! Número: {ticket_number}")
                            # LOG de abertura do ticket
                            id_atv, nome_atv = automation._get_ticket_activity_info(str(ticket_number))
                            _log_ticket_action("OPEN", str(ticket_number), id_atv, nome_atv)
                        else:
                            print(
                                "⚠️ Ticket criado, mas não foi possível obter o número"
                            )
                    else:
                        print("❌ Falha ao criar ticket")
            elif comando == "abrir":
                # Apenas abrir atividade
                if automation.login():
                    automation.abrir_atividade()
            elif comando == "zabbix":
                # Integração com Zabbix: abrir chamado e associar ID ao evento
                # Uso: python open.py zabbix <event_id> <event_value> [descricao]
                if len(sys.argv) < 4:
                    print(
                        "Uso: python open.py zabbix <event_id> <event_value> [descricao]"
                    )
                    return
                event_id = sys.argv[2]
                event_value = sys.argv[3]
                # Junta o restante dos argumentos como observação (descrição do alerta)
                observacao_args = sys.argv[4:] if len(sys.argv) > 4 else []
                observacao = " ".join(observacao_args) if observacao_args else ""
                # Apenas cria chamado se o valor do evento for '1' (problema).
                if str(event_value) != "1":
                    print("Evento não é de problema, nenhum chamado será aberto.")
                    return
                # Executa o fluxo CITSmart: login, adicionar solicitação, salvar pedidos e abrir atividade
                if automation.login():
                    resp_add = automation.adicionar_solicitacao_servico(
                        observacao or "Alerta do Zabbix"
                    )
                    if not resp_add or resp_add.status_code != 200:
                        print("Falha ao adicionar solicitação de serviço.")
                        return
                    resp2, ticket_number = automation.salvar_meus_pedidos()
                    if resp2 and resp2.status_code == 200:
                        # Abre a atividade
                        automation.abrir_atividade()
                        # Caso tenhamos número de ticket, podemos delegar e depois associar id ao evento
                        if ticket_number:
                            print(f"Ticket criado com sucesso! Número: {ticket_number}")
                            # LOG de abertura do ticket
                            id_atv, nome_atv = automation._get_ticket_activity_info(str(ticket_number))
                            _log_ticket_action("OPEN", str(ticket_number), id_atv, nome_atv)
                            # Delegar a tarefa para o grupo 71 (justificativa: observacao)
                            automation.delegar_tarefa(ticket_number, observacao=observacao)
                            # Atribui o número do ticket ao evento Zabbix via reconhecimento
                            zabbix_acknowledge(event_id, ticket_number, observacao)
                        else:
                            print(
                                "⚠️ Ticket criado, mas não foi possível obter o número"
                            )
                    else:
                        print("Falha ao salvar pedidos.")
                return
            else:
                print("Comandos disponíveis:")
                print("  token     - Apenas realizar login")
                print("  fluxo     - Executar fluxo completo")
                print("  adicionar - Apenas adicionar solicitação")
                print("  salvar    - Apenas salvar pedidos")
                print("  abrir     - Apenas abrir atividade")
                print("  zabbix    - Integração com Zabbix (abrir chamado via evento)")
                print("\nUso com observação:")
                print(
                    "  python open.py fluxo 'Descrição do chamado'"
                )
                print(
                    "  python open.py adicionar 'Descrição do chamado'"
                )
                print(
                    "  python open.py zabbix <event_id> <event_value> 'Descrição do chamado'"
                )
        else:
            print("Uso: python open.py [comando] [parametros]")
            print("Comandos disponíveis:")
            print("  token     - Apenas realizar login")
            print("  fluxo     - Executar fluxo completo")
            print("  adicionar - Apenas adicionar solicitação")
            print("  salvar    - Apenas salvar pedidos")
            print("  abrir     - Apenas abrir atividade")
            print(
                "  zabbix    - Integração com Zabbix (abrir chamado via evento)"
            )
            print("\nExemplos:")
            print("  python open.py fluxo 'Problema no sistema'")
            print("  python open.py adicionar 'Erro de conexão'")
            print(
                "  python open.py zabbix 123456 1 'Problema no banco de dados'"
            )

if __name__ == "__main__":
    main()
