INTEGRAÇÃO ZABBIX + CITSMART
===========================

Automatização da abertura e o encerramento de chamados no CITSmart.

--------------------------------------------------------------------------

VISÃO GERAL
-----------

O funcionamento é dividido em dois fluxos:

PROBLEMA
- O Zabbix detecta um problema
- Executa o script open.py
- Um chamado é criado no CITSmart
- O número do ticket é gravado no evento do Zabbix (acknowledgement)

RECUPERAÇÃO
- O trigger retorna ao estado OK
- O Zabbix executa o script close.py
- O chamado é fechado automaticamente no CITSmart
- O evento de problema recebe um ack informando o fechamento

Estrutura do Projeto

**config.py** - Arquivo de configuração para personalização das variáveis principais  
**open.py** - Script responsável pela abertura de chamados  
**close.py** - Script responsável pelo encerramento de chamados  
**tickets.log** - Arquivo de logs com registro das operações realizadas

--------------------------------------------------------------------------

INSTALAÇÃO NO SERVIDOR ZABBIX
-----------------------------

1º - Copie os arquivos config.py, open.py e close.py para o servidor Zabbix ou faça o clone do repositório:
<pre><code>git clone https://github.com/xth3usx/CITSmart-Zabbix-Integration.git</code></pre>

Após o clone, mova os arquivos para: /usr/lib/zabbix/alertscripts

2º - Crie o arquivo de log utilizado pelos scripts:
<pre><code>touch /usr/lib/zabbix/alertscripts/tickets.log</code></pre>

3º - Ajuste de permissões: 
<pre><code>
chmod +x /usr/lib/zabbix/alertscripts/open.py <br>
chmod +x /usr/lib/zabbix/alertscripts/close.py <br>
chmod 644 /usr/lib/zabbix/alertscripts/tickets.log<br>
chown zabbix:zabbix /usr/lib/zabbix/alertscripts/*
</code></pre>

<h2>Pré-requisitos</h2>

<p>Python 3.8+ com a biblioteca <code>requests</code> e <code>urllib3</code>.</p>
<pre><code>pip install requests urllib3</code></pre>

--------------------------------------------------------------------------

CONFIGURAÇÃO (config.py)
------------------------

<h3>CITSmart</h3>

<p>Define como os scripts se conectam ao ambiente CITSmart.</p>

<pre><code>CITSMART_BASE_URL = "https://IP_DO_CITSMART"
CITSMART_FORCED_HOST = "citsmart.homologacao.seudominio.br"

CITSMART_USER = r"dominio\\usuario"
CITSMART_PASSWORD = "senha"
CITSMART_PLATFORM = "WS"

ID_ATIVIDADE = "ID_ATIVIDADE_AQUI"
ID_GRUPO_DESTINO = "ID_GRUPO_DESTINO_AQUI"</code></pre>

<ul>
  <li><strong>CITSMART_BASE_URL</strong>: URL base do portal CITSmart</li>
  <li><strong>CITSMART_FORCED_HOST</strong>: utilizado quando o CITSmart exige header <code>Host</code> específico (proxy / virtual host)</li>
  <li><strong>CITSMART_USER</strong>: usuário do CITSmart</li>
  <li><strong>CITSMART_PASSWORD</strong>: senha do usuário</li>
  <li><strong>CITSMART_PLATFORM</strong>: normalmente <code>WS</code> de "Web Service"</li>
  <li><strong>ID_ATIVIDADE</strong>: ID da atividade do catálogo de serviços utilizada na abertura do chamado</li>
  <li><strong>ID_GRUPO_DESTINO</strong>: ID do grupo para delegação automática do ticket</li>
</ul>

<h3>Zabbix</h3>

<p>Define como os scripts se comunicam com a API do Zabbix.</p>

<pre><code>ZABBIX_API_URL = "https://IP_DO_ZABBIX/zabbix/api_jsonrpc.php"
ZABBIX_API_TOKEN = "TOKEN_DA_API"
ZABBIX_VERIFY_SSL = False</code></pre>

<ul>
  <li><strong>ZABBIX_API_URL</strong>: endpoint da API do Zabbix</li>
  <li><strong>ZABBIX_API_TOKEN</strong>: token da API (não usar usuário/senha)</li>
  <li><strong>ZABBIX_VERIFY_SSL</strong>:
    <ul>
      <li><code>False</code> → certificado autoassinado / ambiente interno</li>
      <li><code>True</code> → certificado válido</li>
    </ul>
  </li>
</ul>

--------------------------------------------------------------------------

TESTES MANUAIS (RECOMENDADO)
----------------------------

Abrir chamado manualmente: <br>
<pre><code>python3 open.py fluxo "Teste manual de abertura"</code></pre>

Fechar chamado manualmente: <br>
<pre><code>python3 close.py fluxo {coloque-id-ticket-aqui}</code></pre>

--------------------------------------------------------------------------

CONFIGURAÇÃO NO ZABBIX
----------------------

SCRIPTS
-------

Configurar dois scripts no zabbix.

Script de abertura:
<pre><code>python3 /usr/lib/zabbix/alertscripts/open.py zabbix {EVENT.ID} {EVENT.VALUE} "{EVENT.NAME} : {EVENT.OPDATA}"</code></pre>

Script de encerramento (Recovery):
<pre><code>python3 /usr/lib/zabbix/alertscripts/close.py zabbix {EVENT.ID} &quot;&lt;div&gt;Problema resolvido automaticamente pelo Zabbix&lt;/div&gt;&quot; &quot;&lt;div&gt;Trigger voltou ao estado OK&lt;/div&gt;&quot;</code></pre>

Exemplo:

<img width="1319" height="365" alt="190" src="https://github.com/user-attachments/assets/87293b9a-3d62-444d-8ab4-c7ca0c856869" />

--------------------------------------------------------------------------

ACTION DE TRIGGER
-----------------

Criar uma Action baseada na severidade, grupo de hosts ou regra desejada.

Exemplo:

<img width="1320" height="249" alt="200" src="https://github.com/user-attachments/assets/0703f682-04da-415d-b786-96ced47d3bf9" />

--------------------------------------------------------------------------

OPERATIONS E RECOVERY
---------------------

Na mesma Action:

- Operations: executar o script de abertura
- Recovery operations: executar o script de encerramento

Exemplo:

<img width="944" height="496" alt="210" src="https://github.com/user-attachments/assets/ed3ddeff-8dd7-4b25-9d57-42ae5b1965db" />

--------------------------------------------------------------------------

Sistema de Logs
---------------

Sempre que um ticket é aberto ou fechado, as informações são registradas automaticamente no arquivo `tickets.log`, contendo:
- Data e hora do evento
- ID do ticket
- Tipo de ação (OPEN/CLOSE)
