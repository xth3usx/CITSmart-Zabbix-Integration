# =====================================================================
# Configuração do CITSmart
# =====================================================================

# URL base do serviço CITSmart (não inclua barra final).
CITSMART_BASE_URL: str = "https://IP-DO-CITSMART"

# Host forçado para CITSmart. Se não for necessário, deixe em branco.
CITSMART_FORCED_HOST: str = "citsmart.dominio.br"

# Usuário de acesso ao CITSmart.
CITSMART_USER: str = r"citsmart.local\usuario.teste"

# Senha correspondente ao usuário do CITSmart.
CITSMART_PASSWORD: str = "SENHA-AQUI"

# Plataforma utilizada no login do CITSmart. Geralmente é "WS" para Web Service, mas pode variar conforme a instalação.
CITSMART_PLATFORM: str = "WS"

# =====================================================================
# Configuração do Zabbix
# =====================================================================

# URL da API JSON-RPC do Zabbix.  Esta é a porta de entrada para todas as chamadas de automação relacionadas a eventos e reconhecimentos.
ZABBIX_API_URL: str = "https://IP-DO-ZABBIX/zabbix/api_jsonrpc.php"

# Token de autenticação da API do Zabbix.  Gere ou forneça o token apropriado para a conta utilizada na automação.
ZABBIX_API_TOKEN: str = "TOKEN-AQUI"

# Indica se a verificação de certificado SSL deve ser realizada nas requisições ao Zabbix.
ZABBIX_VERIFY_SSL: bool = False
