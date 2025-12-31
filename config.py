# =====================================================================
# Configuração do CITSmart
# =====================================================================

# URL base do serviço CITSmart (não inclua barra final).
CITSMART_BASE_URL: str = "https://IP_CITSMART_AQUI"

# Host forçado para CITSmart. Se não for necessário, deixe em branco.
CITSMART_FORCED_HOST: str = "citsmart.homologacao.dominio.br"

# Usuário de acesso ao CITSmart.
CITSMART_USER: str = r"citsmart.local\usuario.teste"

# Senha correspondente ao usuário do CITSmart.
CITSMART_PASSWORD: str = "SENHA_DO_USUÁRIO_CITSMART_AQUI"

# Plataforma utilizada no login do CITSmart.
CITSMART_PLATFORM: str = "WS"

# =====================================================================
# Configurações fixas do fluxo CITSmart (customizáveis pelo usuário)
# =====================================================================

# ID da atividade utilizada na abertura do chamado
ID_ATIVIDADE: str = "1496"

# ID do grupo de destino para delegação automática
ID_GRUPO_DESTINO: str = "71"

# =====================================================================
# Configuração do Zabbix
# =====================================================================

ZABBIX_API_URL: str = "https://IP_ZABBIX_AQUI/zabbix/api_jsonrpc.php"
ZABBIX_API_TOKEN: str = "TOKEN_API_ZABBIX_AQUI"
ZABBIX_VERIFY_SSL: bool = False
