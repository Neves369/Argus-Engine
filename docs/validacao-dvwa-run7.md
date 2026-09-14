# Relatório de segurança

- **Alvo:** pentest-ground.com
- **Run:** #7
- **Status:** completed
- **Achados:** 27

## Superfície

_5 achado(s)_

## [INFO] 1 subdomínio(s) encontrados via certificate transparency

- **Gravidade:** info
- **Categoria:** Superfície de ataque
- **Afetado:** pentest-ground.com
- **Status:** candidate

Registros públicos de certificado (crt.sh) revelam nomes de host adicionais associados a este domínio. Cada um amplia a superfície exposta e vale confirmar se está mesmo em uso, autorizado, e com o mesmo nível de proteção do domínio principal.

**Evidência:** Subdomínios: *.pentest-ground.com

**Remediação:** Para cada subdomínio: confirme se está ativo e autorizado; desative os que não estiverem mais em uso (reduz a superfície de ataque).

**Referências:**
- https://crt.sh/?q=pentest-ground.com

## [INFO] 70 avaliação(ões) pública(s) do domínio pentest-ground.com no urlscan.io

- **Gravidade:** info
- **Categoria:** Superfície de ataque
- **Afetado:** pentest-ground.com
- **Status:** candidate

urlscan.io mantém histórico público de avaliações indexando este domínio. Isso não confirma vulnerabilidade — apenas indica que o domínio já foi observado/avaliado publicamente. Nenhuma avaliação marcada como maliciosa pelo veredito agregado.

**Evidência:** urlscan.io: http://pentest-ground.com/; https://pentest-ground.com:9000/; https://pentest-ground.com/; https://pentest-ground.com:4280/; https://pentest-ground.com:81/

**Remediação:** Revise o conteúdo das avaliações públicas para confirmar se expõem informação sensível do domínio e se os achados ainda são relevantes na configuração atual.

**Referências:**
- https://urlscan.io/domain/pentest-ground.com

## [INFO] 6 host(s) de forward DNS encontrado(s) para pentest-ground.com

- **Gravidade:** info
- **Categoria:** Superfície de ataque
- **Afetado:** pentest-ground.com
- **Status:** candidate

O hostsearch do HackerTarget (forward-DNS passivo) lista nomes de host que resolvem para este domínio. Amplia a superfície de ataque declarada — vale confirmar se cada host está ativo, autorizado e protegido no mesmo nível do domínio principal.

**Evidência:** Hosts: cpanel.pentest-ground.com, playground.pentest-ground.com, wp2shell-fixed.pentest-ground.com, wp2shell-vuln.pentest-ground.com, wp2shell-vuln2.pentest-ground.com, www.pentest-ground.com

**Remediação:** Para cada host: confirme se está ativo e autorizado; remova DNS e serviços que não estejam mais em uso para reduzir a superfície.

**Referências:**
- https://hackertarget.com/host-search/pentest-ground.com

## [INFO] Registro RDAP de pentest-ground.com: registrar=GoDaddy.com, LLC, 2 nameserver(s), registrado em 2019-11-04T15:22:35Z, expira em 2027-11-04T15:22:35Z

- **Gravidade:** info
- **Categoria:** Gestão de domínio
- **Afetado:** pentest-ground.com
- **Status:** candidate

Consultas WHOIS passivas (RDAP, RFC 9083) revelam o registrar, os nameservers e as datas de registro/expiração do domínio. Os nameservers ampliam a superfície de ataque e datas próximas da expiração sinalizam risco de captura/seizure — nada disso é vulnerabilidade em si.

**Evidência:** RDAP: registrar=GoDaddy.com, LLC; 2 nameserver(s); registrado em 2019-11-04T15:22:35Z; expira em 2027-11-04T15:22:35Z; nameservers: NS1.LINODE.COM, NS2.LINODE.COM

**Remediação:** Revise registrar, nameservers e datas de expiração: renove antes do vencimento, monitore mudanças de quem publica o DNS do domínio e remova nameservers não autorizados.

**Referências:**
- https://rdap.org/domain/pentest-ground.com

## [INFO] Stack de tecnologia identificada no alvo

- **Gravidade:** info
- **Categoria:** Superfície de ataque
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

A stack de tecnologia do alvo foi identificada a partir de marcadores observados na resposta (header X-Powered-By e/ou fragmentos no corpo). É uma pista de superfície para orientar a correlação a CVEs — não confirma, por si só, versão vulnerável.

**Evidência:** GET https://pentest-ground.com:4280/ -> tecnologias: PHP; X-Powered-By: PHP/8.5.10

**Remediação:** Use a stack identificada para priorizar a revisão manual e a correlação de versões; minimize a exposição de headers de framework quando possível.

**Referências:**
- https://owasp.org/Top10/

## Configuração

_4 achado(s)_

## [LOW] Headers de segurança ausentes na resposta

- **Gravidade:** low
- **Categoria:** A05:2021 Security Misconfiguration
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

A resposta HTTP não inclui headers de proteção padrão (Content-Security-Policy, Strict-Transport-Security, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy), deixando o alvo exposto a classes de ataque de camada de aplicação. Listado como lead para revisão manual.

**Evidência:** GET https://pentest-ground.com:4280/ -> response sem headers: content-security-policy, permissions-policy, referrer-policy, strict-transport-security, x-content-type-options, x-frame-options

**Remediação:** Adicione os headers de segurança aplicáveis ao tipo de conteúdo servido (pelo menos CSP, X-Frame-Options, nosniff e HSTS em HTTPS).

**Referências:**
- https://owasp.org/Top10/

## [LOW] HSTS ausente em endpoint HTTPS

- **Gravidade:** low
- **Categoria:** A02:2021 Cryptographic Failures
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

O alvo atende em HTTPS mas não emite Strict-Transport-Security, permitindo rebaixamento de protocolo e exposição da primeira conexão de um cliente. Listado como lead para revisão manual.

**Evidência:** GET https://pentest-ground.com:4280/ -> HTTPS sem header Strict-Transport-Security

**Remediação:** Emita Strict-Transport-Security com max-age adequado em toda resposta HTTPS.

**Referências:**
- https://owasp.org/Top10/

## [LOW] Cookies de sessão sem flags de proteção

- **Gravidade:** low
- **Categoria:** A02:2021 Cryptographic Failures
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

Cookies emitidos pelo alvo carecem de um ou mais flags de proteção (Secure, HttpOnly, SameSite), o que facilita intercepção em conexão não criptografada, exposição via script e envio impróprio de origem cruzada. Listado como lead para revisão manual.

**Evidência:** GET https://pentest-ground.com:4280/login.php -> Set-Cookie com flags ausentes: security(secure=False,httponly=False,samesite=None); PHPSESSID(secure=False,httponly=False,samesite=None)

**Remediação:** Emita cookies com Secure e HttpOnly, e defina SameSite de acordo com o uso pretendido (Strict/Lax).

**Referências:**
- https://owasp.org/Top10/

## [INFO] Servidor divulga versão exata no header de resposta

- **Gravidade:** info
- **Categoria:** A05:2021 Security Misconfiguration
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

O alvo expõe a versão exata do servidor web no header HTTP de resposta. Isso reduz o esforço de identificação da stack por um atacante e permite correlacionar o alvo a vulnerabilidades conhecidas dessa versão. A presença da versão é observada aqui; a correlação a CVE exige validação manual da versão real.

**Evidência:** GET https://pentest-ground.com:4280/ -> Server: nginx/1.31.5

**Remediação:** Configure o servidor para não divulgar a versão exata no header Server (ou em banners de componentes atrás do proxy).

**Referências:**
- https://owasp.org/Top10/

## Aplicação

_18 achado(s)_

## [LOW] Erros verbosos expostos em /vulnerabilities/xss_s

- **Gravidade:** low
- **Categoria:** Aplicação (erro verboso)
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

O corpo da resposta contém mensagens de erro internas (stack trace, erro de SQL, notice de linguagem), o que pode revelar estrutura de código, caminhos e detalhes de banco a um atacante. Registrado como lead observado; não é uma confirmação de vulnerabilidade explorável.

**Evidência:** GET https://pentest-ground.com:4280/vulnerabilities/xss_s/ -> corpo contém: stack trace:

**Remediação:** Desative a exibição de erros em produção e devolva páginas de erro genéricas, mantendo o detalhamento apenas em logs internos.

**Referências:**
- https://owasp.org/Top10/

## [INFO] Formulários com entrada de dados em /setup.php

- **Gravidade:** info
- **Categoria:** A03:2021 Injection (leads passivos)
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

Páginas do alvo expõem formulários com campos de entrada (texto/e-mail/senha) e envio a endpoint da aplicação. Esses são vetores em que o tratamento de entrada precisa ser revisado manualmente pelo operador — nenhum teste é executado aqui; é apenas um lead observacional de superfície.

**Evidência:** GET https://pentest-ground.com:4280/setup.php -> formulários: <POST #> fields=[create_db:submit, user_token:hidden] sensíveis=[user_token]

**Remediação:** Revise manualmente o tratamento de entrada destes endpoints (validação, parametrização e codificação de saída).

**Referências:**
- https://owasp.org/Top10/

## [INFO] Formulários com entrada de dados em /vulnerabilities/brute

- **Gravidade:** info
- **Categoria:** A03:2021 Injection (leads passivos)
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

Páginas do alvo expõem formulários com campos de entrada (texto/e-mail/senha) e envio a endpoint da aplicação. Esses são vetores em que o tratamento de entrada precisa ser revisado manualmente pelo operador — nenhum teste é executado aqui; é apenas um lead observacional de superfície.

**Evidência:** GET https://pentest-ground.com:4280/vulnerabilities/brute/ -> formulários: <GET #> fields=[username:text, password:password, Login:submit] sensíveis=[password]

**Remediação:** Revise manualmente o tratamento de entrada destes endpoints (validação, parametrização e codificação de saída).

**Referências:**
- https://owasp.org/Top10/

## [INFO] Formulários com entrada de dados em /vulnerabilities/exec

- **Gravidade:** info
- **Categoria:** A03:2021 Injection (leads passivos)
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

Páginas do alvo expõem formulários com campos de entrada (texto/e-mail/senha) e envio a endpoint da aplicação. Esses são vetores em que o tratamento de entrada precisa ser revisado manualmente pelo operador — nenhum teste é executado aqui; é apenas um lead observacional de superfície.

**Evidência:** GET https://pentest-ground.com:4280/vulnerabilities/exec/ -> formulários: <POST #> fields=[ip:text, Submit:submit]

**Remediação:** Revise manualmente o tratamento de entrada destes endpoints (validação, parametrização e codificação de saída).

**Referências:**
- https://owasp.org/Top10/

## [INFO] Formulários com entrada de dados em /vulnerabilities/csrf

- **Gravidade:** info
- **Categoria:** A03:2021 Injection (leads passivos)
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

Páginas do alvo expõem formulários com campos de entrada (texto/e-mail/senha) e envio a endpoint da aplicação. Esses são vetores em que o tratamento de entrada precisa ser revisado manualmente pelo operador — nenhum teste é executado aqui; é apenas um lead observacional de superfície.

**Evidência:** GET https://pentest-ground.com:4280/vulnerabilities/csrf/ -> formulários: <GET #> fields=[password_new:password, password_conf:password, Change:submit] sensíveis=[password_new, password_conf]

**Remediação:** Revise manualmente o tratamento de entrada destes endpoints (validação, parametrização e codificação de saída).

**Referências:**
- https://owasp.org/Top10/

## [INFO] Parâmetros de entrada refletidos em /vulnerabilities/fi

- **Gravidade:** info
- **Categoria:** A03:2021 Injection (leads passivos)
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

Um ou mais valores de parâmetro de consulta aparecem literalmente no corpo da resposta. Isso indica que a aplicação ecoa entrada do usuário sem codificar — superfície que merece revisão manual de injeção/reflexão. Nenhum payload foi enviado; a reflexão foi observada no conteúdo já retornado.

**Evidência:** GET https://pentest-ground.com:4280/vulnerabilities/fi/?page=include.php -> parâmetros refletidos: page=include.php

**Remediação:** Codifique adequadamente a saída (contexto HTML/atributo/JS/URL) e valide a entrada no servidor.

**Referências:**
- https://owasp.org/Top10/

## [INFO] Formulários com entrada de dados em /vulnerabilities/upload

- **Gravidade:** info
- **Categoria:** A03:2021 Injection (leads passivos)
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

Páginas do alvo expõem formulários com campos de entrada (texto/e-mail/senha) e envio a endpoint da aplicação. Esses são vetores em que o tratamento de entrada precisa ser revisado manualmente pelo operador — nenhum teste é executado aqui; é apenas um lead observacional de superfície.

**Evidência:** GET https://pentest-ground.com:4280/vulnerabilities/upload/ -> formulários: <POST #> fields=[MAX_FILE_SIZE:hidden, uploaded:file, Upload:submit] sensíveis=[MAX_FILE_SIZE, uploaded]

**Remediação:** Revise manualmente o tratamento de entrada destes endpoints (validação, parametrização e codificação de saída).

**Referências:**
- https://owasp.org/Top10/

## [INFO] Formulários com entrada de dados em /vulnerabilities/captcha

- **Gravidade:** info
- **Categoria:** A03:2021 Injection (leads passivos)
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

Páginas do alvo expõem formulários com campos de entrada (texto/e-mail/senha) e envio a endpoint da aplicação. Esses são vetores em que o tratamento de entrada precisa ser revisado manualmente pelo operador — nenhum teste é executado aqui; é apenas um lead observacional de superfície.

**Evidência:** GET https://pentest-ground.com:4280/vulnerabilities/captcha/ -> formulários: <POST #> fields=[step:hidden, password_new:password, password_conf:password, Change:submit] sensíveis=[step, password_new, password_conf]

**Remediação:** Revise manualmente o tratamento de entrada destes endpoints (validação, parametrização e codificação de saída).

**Referências:**
- https://owasp.org/Top10/

## [INFO] Formulários com entrada de dados em /vulnerabilities/sqli

- **Gravidade:** info
- **Categoria:** A03:2021 Injection (leads passivos)
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

Páginas do alvo expõem formulários com campos de entrada (texto/e-mail/senha) e envio a endpoint da aplicação. Esses são vetores em que o tratamento de entrada precisa ser revisado manualmente pelo operador — nenhum teste é executado aqui; é apenas um lead observacional de superfície.

**Evidência:** GET https://pentest-ground.com:4280/vulnerabilities/sqli/ -> formulários: <GET #> fields=[id:text, Submit:submit]

**Remediação:** Revise manualmente o tratamento de entrada destes endpoints (validação, parametrização e codificação de saída).

**Referências:**
- https://owasp.org/Top10/

## [INFO] Formulários com entrada de dados em /vulnerabilities/sqli_blind

- **Gravidade:** info
- **Categoria:** A03:2021 Injection (leads passivos)
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

Páginas do alvo expõem formulários com campos de entrada (texto/e-mail/senha) e envio a endpoint da aplicação. Esses são vetores em que o tratamento de entrada precisa ser revisado manualmente pelo operador — nenhum teste é executado aqui; é apenas um lead observacional de superfície.

**Evidência:** GET https://pentest-ground.com:4280/vulnerabilities/sqli_blind/ -> formulários: <GET #> fields=[id:text, Submit:submit]

**Remediação:** Revise manualmente o tratamento de entrada destes endpoints (validação, parametrização e codificação de saída).

**Referências:**
- https://owasp.org/Top10/

## [INFO] Formulários com entrada de dados em /vulnerabilities/xss_d

- **Gravidade:** info
- **Categoria:** A03:2021 Injection (leads passivos)
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

Páginas do alvo expõem formulários com campos de entrada (texto/e-mail/senha) e envio a endpoint da aplicação. Esses são vetores em que o tratamento de entrada precisa ser revisado manualmente pelo operador — nenhum teste é executado aqui; é apenas um lead observacional de superfície.

**Evidência:** GET https://pentest-ground.com:4280/vulnerabilities/xss_d/ -> formulários: <GET https://pentest-ground.com:4280/vulnerabilities/xss_d/> fields=[default:select]

**Remediação:** Revise manualmente o tratamento de entrada destes endpoints (validação, parametrização e codificação de saída).

**Referências:**
- https://owasp.org/Top10/

## [INFO] Formulários com entrada de dados em /vulnerabilities/xss_r

- **Gravidade:** info
- **Categoria:** A03:2021 Injection (leads passivos)
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

Páginas do alvo expõem formulários com campos de entrada (texto/e-mail/senha) e envio a endpoint da aplicação. Esses são vetores em que o tratamento de entrada precisa ser revisado manualmente pelo operador — nenhum teste é executado aqui; é apenas um lead observacional de superfície.

**Evidência:** GET https://pentest-ground.com:4280/vulnerabilities/xss_r/ -> formulários: <GET #> fields=[name:text]

**Remediação:** Revise manualmente o tratamento de entrada destes endpoints (validação, parametrização e codificação de saída).

**Referências:**
- https://owasp.org/Top10/

## [INFO] Formulários com entrada de dados em /vulnerabilities/csp

- **Gravidade:** info
- **Categoria:** A03:2021 Injection (leads passivos)
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

Páginas do alvo expõem formulários com campos de entrada (texto/e-mail/senha) e envio a endpoint da aplicação. Esses são vetores em que o tratamento de entrada precisa ser revisado manualmente pelo operador — nenhum teste é executado aqui; é apenas um lead observacional de superfície.

**Evidência:** GET https://pentest-ground.com:4280/vulnerabilities/csp/ -> formulários: <POST https://pentest-ground.com:4280/vulnerabilities/csp/> fields=[include:text]

**Remediação:** Revise manualmente o tratamento de entrada destes endpoints (validação, parametrização e codificação de saída).

**Referências:**
- https://owasp.org/Top10/

## [INFO] Formulários com entrada de dados em /vulnerabilities/javascript

- **Gravidade:** info
- **Categoria:** A03:2021 Injection (leads passivos)
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

Páginas do alvo expõem formulários com campos de entrada (texto/e-mail/senha) e envio a endpoint da aplicação. Esses são vetores em que o tratamento de entrada precisa ser revisado manualmente pelo operador — nenhum teste é executado aqui; é apenas um lead observacional de superfície.

**Evidência:** GET https://pentest-ground.com:4280/vulnerabilities/javascript/ -> formulários: <POST https://pentest-ground.com:4280/vulnerabilities/javascript/> fields=[token:hidden, phrase:text, send:submit] sensíveis=[token]

**Remediação:** Revise manualmente o tratamento de entrada destes endpoints (validação, parametrização e codificação de saída).

**Referências:**
- https://owasp.org/Top10/

## [INFO] Formulários com entrada de dados em /security.php

- **Gravidade:** info
- **Categoria:** A03:2021 Injection (leads passivos)
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

Páginas do alvo expõem formulários com campos de entrada (texto/e-mail/senha) e envio a endpoint da aplicação. Esses são vetores em que o tratamento de entrada precisa ser revisado manualmente pelo operador — nenhum teste é executado aqui; é apenas um lead observacional de superfície.

**Evidência:** GET https://pentest-ground.com:4280/security.php -> formulários: <POST #> fields=[security:select, seclev_submit:submit, user_token:hidden] sensíveis=[user_token]

**Remediação:** Revise manualmente o tratamento de entrada destes endpoints (validação, parametrização e codificação de saída).

**Referências:**
- https://owasp.org/Top10/

## [INFO] Formulários com entrada de dados em /login.php

- **Gravidade:** info
- **Categoria:** A03:2021 Injection (leads passivos)
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

Páginas do alvo expõem formulários com campos de entrada (texto/e-mail/senha) e envio a endpoint da aplicação. Esses são vetores em que o tratamento de entrada precisa ser revisado manualmente pelo operador — nenhum teste é executado aqui; é apenas um lead observacional de superfície.

**Evidência:** GET https://pentest-ground.com:4280/login.php -> formulários: <POST login.php> fields=[username:text, password:password, Login:submit, user_token:hidden] sensíveis=[password, user_token]

**Remediação:** Revise manualmente o tratamento de entrada destes endpoints (validação, parametrização e codificação de saída).

**Referências:**
- https://owasp.org/Top10/

## [INFO] Parâmetros de entrada refletidos em /instructions.php

- **Gravidade:** info
- **Categoria:** A03:2021 Injection (leads passivos)
- **Afetado:** pentest-ground.com:4280
- **Status:** candidate

Um ou mais valores de parâmetro de consulta aparecem literalmente no corpo da resposta. Isso indica que a aplicação ecoa entrada do usuário sem codificar — superfície que merece revisão manual de injeção/reflexão. Nenhum payload foi enviado; a reflexão foi observada no conteúdo já retornado.

**Evidência:** GET https://pentest-ground.com:4280/instructions.php?doc=readme -> parâmetros refletidos: doc=readme

**Remediação:** Codifique adequadamente a saída (contexto HTML/atributo/JS/URL) e valide a entrada no servidor.

**Referências:**
- https://owasp.org/Top10/

## [INFO] 24 módulo(s)/rota(s) internos descobertos durante o crawl

- **Gravidade:** info
- **Categoria:** Aplicação (módulos/rotas observados)
- **Afetado:** pentest-ground.com
- **Status:** candidate

O crawl observacional encontrou páginas/rotas internas do mesmo host além da raiz. Cada módulo amplia a superfície de aplicação e vale revisão manual de tratamento de entrada e autorização. Nenhum teste foi executado — são apenas destinos observados.

**Evidência:** Rotas: /, /dvwa/css/main.css, /favicon.ico, /instructions.php, /setup.php, /vulnerabilities/brute, /vulnerabilities/exec, /vulnerabilities/csrf, /vulnerabilities/fi, /vulnerabilities/upload, /vulnerabilities/captcha, /vulnerabilities/sqli, /vulnerabilities/sqli_blind, /vulnerabilities/weak_id, /vulnerabilities/xss_d, /vulnerabilities/xss_r, /vulnerabilities/xss_s, /vulnerabilities/csp, /vulnerabilities/javascript, /vulnerabilities/open_redirect (+4 outro(s))

**Remediação:** Revise cada módulo descoberto: confirme se deve estar acessível, se exige autenticação e se o tratamento de entrada é adequado.

**Referências:**
- https://owasp.org/Top10/

## Observabilidade

- Tokens: 450
- Custo: $0.0000
- Confiança do grafo: 0.6000000000000001
- Motivo de parada: completed
