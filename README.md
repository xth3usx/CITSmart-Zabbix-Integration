INTEGRAÇÃO ZABBIX + CITSMART
===========================

Este projeto automatiza a abertura e o encerramento de chamados no CITSmart
a partir de eventos do Zabbix, utilizando scripts Python executados via Actions.

O objetivo é reduzir esforço operacional e padronizar o processo de atendimento.

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

--------------------------------------------------------------------------

INSTALAÇÃO NO SERVIDOR ZABBIX
-----------------------------

Os três scripts DEVEM ficar preferencialmente no diretório:
/usr/lib/zabbix/alertscripts

Ajustar as permissões:

chmod +x /usr/lib/zabbix/alertscripts/open.py <br>
chmod +x /usr/lib/zabbix/alertscripts/close.py <br>
chown zabbix:zabbix /usr/lib/zabbix/alertscripts/*

--------------------------------------------------------------------------

CONFIGURAÇÃO (config.py)
------------------------

Toda a configuração do projeto está centralizada no arquivo config.py.

--------------------------------------------------------------------------

TESTES MANUAIS (RECOMENDADO)
----------------------------

Abrir chamado manualmente: <br>
<pre><code>python3 open.py fluxo "Teste manual de abertura"</code></pre>

Fechar chamado manualmente: <br>
<pre><code>python3 close.py fluxo <id-ticket></code></pre>

--------------------------------------------------------------------------

CONFIGURAÇÃO NO ZABBIX
----------------------

SCRIPTS
-------

Cadastrar dois scripts no Zabbix:

Script de abertura:
python3 /usr/lib/zabbix/alertscripts/open.py zabbix {EVENT.ID} {EVENT.VALUE} "{EVENT.NAME} : {EVENT.OPDATA}"

Script de encerramento:
python3 /usr/lib/zabbix/alertscripts/close.py zabbix {EVENT.ID}
"<div>Problema resolvido automaticamente pelo Zabbix</div>"
"<div>Trigger voltou ao estado OK</div>"

<img width="1319" height="365" alt="190" src="https://github.com/user-attachments/assets/87293b9a-3d62-444d-8ab4-c7ca0c856869" />

--------------------------------------------------------------------------

ACTION DE TRIGGER
-----------------

Criar uma Action baseada na severidade, grupo de hosts ou regra desejada.

<img width="1320" height="249" alt="200" src="https://github.com/user-attachments/assets/0703f682-04da-415d-b786-96ced47d3bf9" />

--------------------------------------------------------------------------

OPERATIONS E RECOVERY
---------------------

Na mesma Action:

- Operations: executar o script de abertura
- Recovery operations: executar o script de encerramento

<img width="944" height="496" alt="210" src="https://github.com/user-attachments/assets/ed3ddeff-8dd7-4b25-9d57-42ae5b1965db" />

--------------------------------------------------------------------------

LOGS
----

O script de fechamento grava logs em: /tmp/citsmart_close_zabbix.log

--------------------------------------------------------------------------

BOAS PRÁTICAS
-------------

- Utilize usuário dedicado no CITSmart
- Restrinja permissões do arquivo config.py
