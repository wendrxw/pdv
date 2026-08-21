# PDV

Esse projeto tem como objetivo criar um sistema PDV para controle de vendas, entrada e saida de caixa, controle de estoque e controle financeiro.

## Motivação

- Um casal de amigos precisa de um sistema completo para auxilia-los em sua nova empresa, mas os sistemas atuais são lentos, são feitos para desktop ou muito caros. A ideia aqui é fazer algo completo, funcional e sem cobrar um absurdo por mês.

## Detalhes tecnicos

- Irei usar um servidor caseiro, com nginx e cloudflare tunnel (via cloudflared);
- Iremos desenvolver um sistema web;
- Iremos usar python, django, djangorestframework (DRF), postgresql, redis, celery, django templates, tailwindcss, html, js, css;
- Toda a documentação do projeto deverá ser lida a cada tarefa atuada e a mesma deverá ser atualizada com base na ultima aplicação feita;
- O sistema irá usar como ferramentas externas um leitor de codigo de barras e uma impressora termica, para impressão fiscal e não fiscal;
- Após cada tarefa, o agent deve executar uma analise de vulnerabilidade, atualização de bibliotecas e atualização na documentação de referencia;
- Iremos usar bcrypt para hash de senhas;
- Iremos usar UUID para codigo unico de registros nas tabelas do banco de dados;
- A conta da aplicação será criada pela equipe administradora do sistema, nunca pelo usuário;
- Para gerenciamento interno (equipe administradora), iremos usar o django admin;
- Todos os models, views e afins deverão estar presentes no painel admin;
- 

# Implementação do módulo fiscal NFC-e — SEFAZ-SP

Você é o agente responsável por implementar o módulo fiscal de um sistema PDV em Python.

## 1. Objetivo

Implementar um módulo completo para emissão de **NFC-e (Nota Fiscal de Consumidor Eletrônica), modelo 65**, inicialmente direcionado para **SEFAZ-SP**, utilizando o ambiente de homologação.

O sistema deverá:

* gerar a NFC-e;
* montar o XML conforme o leiaute oficial vigente;
* validar o XML contra os XSD oficiais;
* assinar digitalmente o XML com certificado A1;
* transmitir para a SEFAZ-SP;
* interpretar a resposta;
* armazenar XML e protocolo;
* consultar uma NFC-e;
* cancelar uma NFC-e;
* inutilizar numeração;
* consultar status do serviço;
* gerar informações necessárias para impressão do DANFE-NFC-e;
* permitir posteriormente expansão para outras UFs.

## 2. Regra fundamental

NÃO invente regras fiscais.

Antes de implementar qualquer parte relacionada ao XML, leia e utilize como fonte primária:

1. Portal Nacional da NF-e;
2. Manual de Orientação do Contribuinte vigente;
3. XSDs oficiais;
4. Notas Técnicas vigentes;
5. documentação oficial da SEFAZ-SP;
6. documentação oficial referente à NFC-e de São Paulo.

Utilize sempre a versão vigente da documentação encontrada nessas fontes.

Não copie código de blogs ou exemplos antigos sem verificar se continuam válidos.

O Portal Nacional deve ser tratado como fonte primária para leiautes, schemas e Notas Técnicas. A SEFAZ-SP deve ser tratada como fonte primária para os Web Services específicos de São Paulo.

## 3. Arquitetura

O módulo fiscal deve ser isolado do restante do PDV.

Criar uma camada semelhante a:

```
fiscal/
    domain/
    application/
    infrastructure/
    sefaz/
    nfe/
    nfce/
    certificates/
    xml/
    signing/
    printing/
    exceptions/
    tests/
```

Evitar que regras fiscais fiquem espalhadas pelas views, controllers ou modelos do PDV.

O restante do sistema deverá interagir com o módulo fiscal através de serviços bem definidos.

Exemplo conceitual:

```
FiscalService.emitir_nfce(venda)

FiscalService.consultar_nfce(chave)

FiscalService.cancelar_nfce(chave, justificativa)

FiscalService.inutilizar(numero_inicial, numero_final, justificativa)

FiscalService.status_sefaz()
```

## 4. Modelo de domínio

Criar entidades/modelos para representar pelo menos:

* estabelecimento;
* certificado digital;
* configuração fiscal;
* série fiscal;
* numeração;
* NFC-e;
* itens da NFC-e;
* pagamentos;
* impostos;
* eventos fiscais;
* protocolo de autorização;
* status fiscal.

A NFC-e deve possuir estados claramente definidos.

Exemplo:

```
PENDENTE
GERADA
ASSINADA
TRANSMITINDO
AUTORIZADA
REJEITADA
CANCELADA
DENEGADA
CONTINGENCIA
```

Não misturar status da venda com status fiscal.

## 5. Certificado digital

Implementar suporte inicialmente para certificado **A1 em formato PFX/P12**.

O certificado nunca deve ser armazenado em texto puro no banco.

Criar uma abstração:

```
CertificateProvider
```

que permita posteriormente suportar outros mecanismos.

O sistema deverá conseguir:

* carregar o certificado;
* validar validade;
* extrair certificado público;
* utilizar a chave privada para assinatura;
* detectar certificado expirado;
* produzir mensagens de erro claras.

Nunca registrar a senha do certificado em logs.

Nunca registrar a chave privada.

## 6. Geração da NFC-e

Criar um gerador de XML baseado em objetos de domínio, e não através de concatenação manual de strings.

Exemplo conceitual:

```
NFCe
  ├── ide
  ├── emit
  ├── dest
  ├── det
  ├── total
  ├── transp
  ├── pag
  └── infAdic
```

A implementação deve respeitar exatamente o leiaute oficial vigente.

Os campos fiscais não devem receber valores fictícios automaticamente.

Se determinado dado fiscal for obrigatório, o sistema deve exigir que ele esteja configurado.

## 7. Chave de acesso

Implementar geração da chave de acesso da NFC-e conforme as regras oficiais.

A chave deve ser composta utilizando os campos oficiais do documento.

Implementar também:

* cálculo do dígito verificador;
* validação da chave;
* armazenamento da chave;
* consulta por chave.

Criar testes unitários específicos para o cálculo da chave e do DV.

## 8. Assinatura XML

Implementar assinatura digital conforme o padrão exigido pela NF-e/NFC-e.

A assinatura deve:

* utilizar o certificado A1;
* assinar o elemento correto;
* utilizar o algoritmo exigido pela especificação vigente;
* inserir a assinatura no XML no local correto;
* permitir validação posterior.

Criar testes que verifiquem que o XML assinado pode ser validado criptograficamente.

Não implementar criptografia própria.

## 9. Validação XSD

Implementar validação do XML contra os schemas oficiais.

A aplicação deverá diferenciar:

```
XML inválido estruturalmente
```

de:

```
XML válido estruturalmente, mas rejeitado pela SEFAZ
```

O erro de validação deve indicar:

* campo;
* caminho XML;
* motivo;
* schema/regra relacionada quando disponível.

## 10. Comunicação com SEFAZ

Criar uma abstração:

```
SefazClient
```

com operações:

```
status_servico()
autorizar()
consultar_protocolo()
receber_evento()
inutilizar()
```

A implementação inicial será exclusivamente para:

```
UF = SP
modelo = 65
ambiente = homologação
```

Utilizar os Web Services oficiais atuais da SEFAZ-SP.

Não deixar URLs espalhadas pelo código.

Configurar através de settings:

```
SEFAZ_UF
SEFAZ_AMBIENTE
SEFAZ_CERTIFICATE
SEFAZ_CERTIFICATE_PASSWORD
SEFAZ_TIMEOUT
```

As URLs devem ser definidas em uma camada específica de configuração por UF/ambiente.

## 11. SOAP

Implementar comunicação SOAP conforme o Web Service oficial.

A implementação deve lidar corretamente com:

* TLS;
* certificado;
* SOAP envelope;
* namespace;
* versão do serviço;
* timeout;
* falhas de conexão;
* indisponibilidade da SEFAZ;
* respostas inválidas;
* erros SOAP.

Não considerar HTTP 200 como sinônimo de autorização.

A decisão final deve ser baseada no conteúdo da resposta da SEFAZ.

## 12. Autorização

O fluxo deve ser:

```
venda
  ↓
gerar NFC-e
  ↓
validar XML
  ↓
assinar
  ↓
validar assinatura
  ↓
transmitir
  ↓
interpretar resposta
  ↓
autorizado/rejeitado/erro
```

Se autorizado:

* armazenar XML autorizado;
* armazenar protocolo;
* armazenar chave;
* armazenar data/hora;
* atualizar status;
* disponibilizar impressão.

Se rejeitado:

* armazenar a resposta da SEFAZ;
* armazenar código da rejeição;
* armazenar motivo;
* manter a NFC-e como rejeitada;
* permitir correção e nova tentativa quando aplicável.

## 13. Idempotência

Este ponto é obrigatório.

Uma queda de conexão após o envio não pode fazer o PDV simplesmente emitir outra NFC-e.

Implementar mecanismos para lidar com:

* timeout;
* conexão perdida;
* resposta perdida;
* duplicidade;
* consulta posterior da chave.

O sistema deverá conseguir descobrir se uma NFC-e foi autorizada mesmo quando a resposta original não chegou ao PDV.

## 14. Consulta

Implementar consulta da NFC-e pela chave.

A consulta deverá atualizar o estado local conforme a resposta oficial.

Exemplo:

```
consultar(chave)
```

deve retornar um objeto estruturado contendo:

```
status
codigo
motivo
protocolo
xml
data_autorizacao
```

quando essas informações estiverem disponíveis.

## 15. Cancelamento

Implementar cancelamento através do mecanismo oficial de eventos da NF-e/NFC-e.

Exigir:

* chave;
* justificativa;
* certificado;
* identificação do estabelecimento;
* ambiente.

Validar as regras e prazos oficiais vigentes antes da implementação.

Não assumir prazos antigos encontrados em exemplos da internet.

## 16. Inutilização

Implementar inutilização de numeração.

Exigir:

* série;
* número inicial;
* número final;
* justificativa.

Validar:

* sequência;
* intervalo;
* justificativa;
* regras fiscais vigentes.

## 17. Contingência

NÃO implementar contingência como primeira etapa.

Primeiro deixar completamente funcional:

```
homologação
↓
geração
↓
assinatura
↓
autorização
↓
consulta
↓
cancelamento
↓
inutilização
```

Depois criar uma etapa separada para contingência, estudando especificamente a modalidade aplicável à NFC-e em São Paulo e as regras vigentes.

Não assumir que qualquer modalidade histórica de contingência continua válida.

## 18. QR Code / DANFE-NFC-e

Após autorização, implementar geração das informações necessárias para o DANFE-NFC-e.

O QR Code deve seguir exatamente a especificação vigente da NFC-e.

Não utilizar implementação antiga encontrada em exemplos de terceiros.

Separar:

```
FiscalDocument
```

de:

```
DanfeRenderer
```

O documento fiscal deve existir independentemente da forma de impressão.

## 19. Impressora

O PDV poderá utilizar uma impressora térmica como a Bematech MP-4200 HS.

Criar uma abstração:

```
Printer
```

com implementação inicial para impressão térmica.

A emissão fiscal NÃO pode depender da impressora.

Fluxo:

```
SEFAZ autorizou
      ↓
documento fiscal armazenado
      ↓
gerar DANFE
      ↓
imprimir
```

Se a impressora falhar depois da autorização, a NFC-e continua autorizada.

## 20. Persistência

Nunca depender exclusivamente do XML como armazenamento.

Persistir metadados estruturados:

```
chave_acesso
numero
serie
modelo
ambiente
uf
status
protocolo
data_emissao
data_autorizacao
valor_total
motivo_rejeicao
codigo_rejeicao
```

Guardar também:

* XML enviado;
* XML assinado;
* XML autorizado;
* XML de eventos;
* respostas relevantes da SEFAZ.

## 21. Segurança

Nunca registrar em logs:

* senha do certificado;
* chave privada;
* certificado completo desnecessariamente;
* dados sensíveis desnecessários.

Evitar armazenar certificado em diretório público.

Permissões de arquivos devem ser restritas.

Não colocar senha do certificado diretamente no código.

Utilizar variáveis de ambiente ou mecanismo seguro de configuração.

## 22. Observabilidade

Criar logs estruturados.

Cada operação fiscal deve possuir um identificador de correlação.

Exemplo:

```
fiscal_operation_id
```

Registrar:

* início da operação;
* tipo da operação;
* chave quando já disponível;
* ambiente;
* UF;
* duração;
* resultado;
* código da SEFAZ;
* motivo da rejeição.

Nunca registrar segredo do certificado.

## 23. Testes

Criar testes unitários para:

* chave de acesso;
* dígito verificador;
* geração do XML;
* validação XSD;
* assinatura;
* leitura do certificado;
* parsing da resposta SOAP;
* interpretação de rejeições;
* cancelamento;
* inutilização.

Criar testes de integração separados.

Não fazer testes reais de produção automaticamente.

## 24. Ambiente de homologação

Criar configuração explícita:

```
SEFAZ_AMBIENTE=HOMOLOGACAO
```

O sistema deve impedir acidentalmente que testes utilizem produção.

Exibir claramente:

```
AMBIENTE DE HOMOLOGAÇÃO
```

na interface administrativa.

Produção somente poderá ser habilitada através de configuração explícita.

## 25. Configuração fiscal

Criar uma tela administrativa para configurar:

* CNPJ;
* razão social;
* nome fantasia;
* IE;
* endereço;
* município;
* código IBGE;
* UF;
* CRT;
* série NFC-e;
* próximo número;
* certificado;
* ambiente;
* CSC/token quando exigido pela configuração vigente;
* demais parâmetros fiscais necessários.

Não criar campos fiscais arbitrários. Eles devem corresponder à documentação oficial vigente.

## 26. Separação de responsabilidades

Não colocar tudo em uma classe gigante como:

```
NFCeManager
```

Separar responsabilidades:

```
NFCeBuilder
NFCeValidator
XMLSigner
CertificateProvider
SefazClient
SefazResponseParser
FiscalRepository
NFCeService
DanfeRenderer
```

Cada componente deve ter responsabilidade única.

## 27. Extensibilidade

Embora a primeira implementação seja SP/NFC-e, preparar a arquitetura para:

```
SP
RJ
MG
PR
etc.
```

A interface deve permitir:

```
SefazProvider
```

com implementações específicas por UF quando necessário.

Não criar abstrações excessivamente complexas antes de existir necessidade real.

## 28. Documentação

Criar documentação explicando:

1. Como configurar o certificado A1.
2. Como configurar uma empresa.
3. Como configurar a série.
4. Como configurar homologação.
5. Como emitir uma NFC-e.
6. Como interpretar rejeições.
7. Como consultar uma NFC-e.
8. Como cancelar.
9. Como inutilizar.
10. Como mudar para produção.
11. Como fazer backup dos XMLs.
12. Como restaurar o sistema.

## 29. Critérios de aceite

A implementação somente será considerada concluída quando for possível:

### Cenário 1

Criar uma venda no PDV.

### Cenário 2

Transformar a venda em NFC-e.

### Cenário 3

Gerar XML válido.

### Cenário 4

Assinar o XML com certificado A1.

### Cenário 5

Validar o XML contra o XSD oficial.

### Cenário 6

Transmitir para SEFAZ-SP em homologação.

### Cenário 7

Receber uma autorização válida.

### Cenário 8

Persistir:

```
chave
protocolo
XML
status
```

### Cenário 9

Consultar a NFC-e posteriormente.

### Cenário 10

Cancelar uma NFC-e autorizada em homologação, conforme as regras vigentes.

### Cenário 11

Simular uma rejeição e mostrar corretamente:

```
código
motivo
campo relacionado
```

### Cenário 12

Simular perda de conexão após transmissão e garantir que o sistema não gere uma segunda NFC-e indevidamente.

## 30. Ordem de implementação

Não implemente tudo de uma vez.

Faça em fases:

### Fase 1 — Fundação

* estrutura fiscal;
* modelos;
* configurações;
* certificado;
* numeração.

### Fase 2 — XML

* domínio;
* geração;
* schemas;
* validação.

### Fase 3 — Assinatura

* certificado A1;
* assinatura XML;
* testes criptográficos.

### Fase 4 — SEFAZ

* SOAP;
* status;
* autorização;
* parsing das respostas.

### Fase 5 — Persistência

* XML;
* protocolo;
* status;
* auditoria.

### Fase 6 — Operações fiscais

* consulta;
* cancelamento;
* inutilização.

### Fase 7 — DANFE

* QR Code;
* impressão;
* integração com impressora térmica.

### Fase 8 — Produção

Somente depois que todos os testes de homologação estiverem funcionando.

## 31. Regra final

Antes de escrever código:

1. inspecione o projeto existente;
2. identifique framework, banco e arquitetura;
3. descubra como o PDV representa uma venda;
4. identifique produtos, clientes e pagamentos existentes;
5. não crie estruturas duplicadas;
6. apresente um plano de implementação;
7. implemente uma fase por vez;
8. execute os testes após cada fase;
9. não avance se os testes anteriores estiverem quebrados.

Ao encontrar uma dúvida fiscal, NÃO invente.

Pare e consulte a documentação oficial vigente.

O objetivo é construir uma implementação fiscal real, auditável e preparada para homologação, e não apenas um XML que pareça uma NFC-e.



# Implementação do módulo de Produtos, Estoque e Inventário

Você é responsável por implementar o módulo de **cadastro de produtos, controle de estoque e inventário** de um sistema de gestão/PDV.

## 1. Stack obrigatória

O projeto utiliza:

* Python
* Django
* Django Templates
* HTML
* JavaScript
* CSS
* TailwindCSS

Não introduza frameworks frontend como React, Vue, Angular ou similares.

Utilize Django Templates como mecanismo principal de renderização.

Utilize JavaScript apenas quando necessário para interações dinâmicas.

Utilize TailwindCSS para estilização da interface.

Antes de implementar qualquer coisa, inspecione a estrutura atual do projeto e reutilize os padrões existentes.

---

# 2. Multi-tenancy — requisito crítico

A aplicação é **multi-tenant**.

Esse requisito deve ser tratado como prioridade máxima.

Todos os dados relacionados a:

* produtos;
* categorias;
* estoque;
* movimentações;
* inventários;
* fornecedores;
* códigos;
* preços;

devem pertencer a um tenant.

Um usuário de um tenant NUNCA pode:

* visualizar produtos de outro tenant;
* alterar produtos de outro tenant;
* excluir produtos de outro tenant;
* visualizar estoque de outro tenant;
* criar movimentações em outro tenant;
* visualizar inventários de outro tenant;
* consultar códigos de outro tenant.

Não confiar apenas em filtros enviados pelo frontend.

O backend deve determinar o tenant através do mecanismo de tenancy já existente no projeto.

Antes de implementar:

1. identificar como o projeto atual representa o tenant;
2. identificar como o tenant é obtido no request;
3. identificar como usuários estão relacionados ao tenant;
4. identificar os padrões atuais de isolamento;
5. reutilizar a arquitetura existente.

NÃO criar um segundo sistema de tenancy.

---

# 3. Regra de segurança multi-tenant

Nunca fazer consultas perigosas como:

```
Product.objects.get(uuid=uuid)
```

se isso puder permitir acesso cross-tenant.

Preferir sempre consultas condicionadas ao tenant atual:

```
Product.objects.get(
    tenant=current_tenant,
    uuid=uuid
)
```

ou utilizar o mecanismo de isolamento já existente no projeto.

Todos os endpoints/views/services devem possuir proteção equivalente.

Não confiar em:

* UUID;
* ID;
* slug;
* código de barras;
* SKU;

como mecanismo de isolamento.

---

# 4. Objetivo do módulo

Criar um módulo completo para:

* cadastro de produtos;
* edição de produtos;
* exclusão/desativação de produtos;
* consulta de produtos;
* pesquisa;
* filtros;
* categorias;
* código interno;
* SKU;
* código de barras;
* geração de código de barras;
* preços;
* estoque;
* movimentação de estoque;
* entrada de mercadorias;
* saída de mercadorias;
* ajustes;
* inventário;
* histórico;
* auditoria.

O módulo deve estar preparado para integração futura com o PDV e módulo fiscal.

---

# 5. Produto

O model principal deverá obrigatoriamente possuir:

```
uuid
nome
data_cadastro
tamanho
observacao
```

Onde:

```
uuid
```

será um UUID único.

A data de cadastro deve ser preenchida automaticamente pelo backend.

Utilizar timezone-aware datetime de acordo com a configuração do Django.

Exemplo conceitual:

```
uuid = UUIDField(
    default=uuid.uuid4,
    editable=False,
    unique=True
)

data_cadastro = DateTimeField(
    auto_now_add=True
)
```

Não utilizar UUID gerado pelo frontend.

O UUID deve ser gerado pelo backend.

---

# 6. Campos adicionais recomendados

Além dos campos obrigatórios, adicionar campos necessários para um sistema de loja/PDV.

Sugestão inicial:

```
sku
codigo_barras
nome
descricao
tamanho
unidade_medida
categoria
marca
preco_custo
preco_venda
estoque_minimo
estoque_maximo
ativo
observacao
data_cadastro
data_atualizacao
```

Avaliar cuidadosamente se cada campo realmente pertence ao produto.

Não adicionar campos apenas por adicionar.

---

# 7. Identificadores

O sistema deverá trabalhar com três conceitos diferentes.

## UUID

Identificador técnico.

Exemplo:

```
550e8400-e29b-41d4-a716-446655440000
```

Deve ser único globalmente.

## SKU

Código interno/comercial.

Exemplo:

```
CAM-001-PRETO-M
```

O SKU deve ser único dentro do tenant.

Não assumir unicidade global entre tenants.

## Código de barras

Código utilizado para leitura no PDV.

Deve possuir unicidade dentro do tenant.

Não utilizar UUID diretamente como código de barras.

---

# 8. Código de barras

Implementar geração de código de barras para produtos.

Para produtos internos da loja, utilizar inicialmente **EAN-13**, respeitando as regras de cálculo do dígito verificador.

IMPORTANTE:

Não apresentar um EAN-13 interno como se fosse um GTIN oficialmente registrado.

O sistema deve deixar claro que códigos gerados internamente são destinados ao uso interno da loja/PDV.

Criar um serviço:

```
BarcodeService
```

com responsabilidades como:

```
generate()
validate()
calculate_check_digit()
```

O código de barras deve:

* possuir 13 dígitos;
* ser numericamente válido;
* possuir dígito verificador correto;
* ser único dentro do tenant;
* possuir índice no banco;
* não ser reutilizado automaticamente após exclusão lógica do produto.

A geração deve ocorrer no backend.

Não confiar em JavaScript para gerar o código definitivo.

---

# 9. Renderização do código de barras

O sistema deve conseguir gerar uma representação visual do código de barras para impressão.

Criar uma abstração:

```
BarcodeRenderer
```

que possa gerar:

* SVG;
* PNG, quando necessário;
* representação adequada para impressão.

Preferir SVG quando possível.

Não armazenar necessariamente a imagem do código de barras no banco.

O código numérico deve ser a fonte da verdade.

A imagem pode ser gerada dinamicamente.

---

# 10. Categorias

Criar cadastro de categorias.

Exemplo:

```
Categoria
    uuid
    nome
    descricao
    ativo
    data_cadastro
    data_atualizacao
    tenant
```

A categoria deve pertencer ao tenant.

O nome pode possuir unicidade dentro do tenant.

Não permitir que um produto de um tenant seja associado a uma categoria de outro tenant.

---

# 11. Marca

Se fizer sentido para o domínio existente, criar cadastro de marcas.

Exemplo:

```
Marca
    uuid
    nome
    ativo
    tenant
    data_cadastro
    data_atualizacao
```

A marca deve ser isolada por tenant.

Não obrigar marca caso o negócio não utilize esse conceito.

---

# 12. Unidade de medida

Criar uma estrutura para unidade de medida ou utilizar choices quando isso for suficiente.

Exemplos:

```
UN
KG
G
L
ML
CX
PCT
```

A escolha deve ser compatível com futuras integrações fiscais.

Não utilizar textos arbitrários espalhados pelo sistema.

---

# 13. Preços

O produto deve possuir inicialmente:

```
preco_custo
preco_venda
```

Utilizar `DecimalField`.

Nunca utilizar `float` para valores monetários.

Definir precisão adequada para valores brasileiros.

Exemplo conceitual:

```
DecimalField(
    max_digits=12,
    decimal_places=2
)
```

O preço de venda deve ser >= 0.

O preço de custo deve ser >= 0.

Não permitir valores monetários negativos sem uma justificativa de domínio explícita.

---

# 14. Estoque

NÃO implementar estoque apenas como:

```
produto.estoque = 50
```

O estoque deve possuir histórico de movimentações.

Criar uma estrutura semelhante a:

```
Estoque
    uuid
    tenant
    produto
    quantidade
    estoque_minimo
    estoque_maximo
    data_atualizacao
```

E:

```
MovimentacaoEstoque
    uuid
    tenant
    produto
    tipo
    quantidade
    saldo_anterior
    saldo_posterior
    motivo
    referencia
    usuario
    data_criacao
```

---

# 15. Tipos de movimentação

Criar tipos claramente definidos.

Por exemplo:

```
ENTRADA
SAIDA
AJUSTE_POSITIVO
AJUSTE_NEGATIVO
VENDA
DEVOLUCAO
CANCELAMENTO_VENDA
INVENTARIO
```

Não permitir que qualquer string seja utilizada como tipo de movimentação.

---

# 16. Regra fundamental do estoque

Toda alteração de estoque deve gerar uma movimentação.

Nunca alterar diretamente:

```
estoque.quantidade
```

fora do serviço responsável pelo controle de estoque.

Criar:

```
EstoqueService
```

com operações semelhantes a:

```
adicionar_estoque()
remover_estoque()
ajustar_estoque()
registrar_venda()
registrar_devolucao()
aplicar_inventario()
```

O serviço deve ser responsável por manter a consistência.

---

# 17. Transações

Operações de estoque devem utilizar transações atômicas.

Exemplo conceitual:

```
transaction.atomic()
```

A atualização do saldo e a criação da movimentação devem ocorrer na mesma transação.

Se uma falhar:

```
nenhuma alteração deve permanecer.
```

---

# 18. Concorrência

Considerar concorrência.

Duas operações simultâneas não podem causar:

* saldo incorreto;
* estoque negativo indevido;
* perda de movimentação.

Utilizar mecanismos apropriados do banco de dados, como:

```
select_for_update()
```

quando necessário.

Não confiar apenas na lógica Python para garantir consistência concorrente.

---

# 19. Estoque negativo

Criar configuração por tenant para determinar se estoque negativo é permitido.

Exemplo:

```
permitir_estoque_negativo
```

Se desabilitado:

```
quantidade disponível = 2
saída solicitada = 3
```

deve resultar em erro de domínio.

Nunca deixar o saldo ficar negativo simplesmente porque a operação aconteceu simultaneamente.

---

# 20. Entrada de estoque

Criar interface para registrar entrada.

Campos:

* produto;
* quantidade;
* custo unitário;
* fornecedor opcional;
* documento/referência opcional;
* observação;
* usuário responsável.

Ao confirmar:

1. validar produto;
2. validar tenant;
3. validar quantidade;
4. iniciar transação;
5. obter estoque com lock;
6. registrar saldo anterior;
7. atualizar saldo;
8. registrar movimentação;
9. finalizar transação.

---

# 21. Saída de estoque

Criar operação equivalente.

Ao retirar:

1. validar quantidade;
2. verificar estoque;
3. aplicar regra de estoque negativo;
4. bloquear registro;
5. atualizar saldo;
6. registrar movimentação.

---

# 22. Fornecedor

Se o projeto ainda não possuir fornecedor, criar estrutura básica:

```
Fornecedor
    uuid
    razao_social
    nome_fantasia
    documento
    email
    telefone
    ativo
    observacao
    tenant
    data_cadastro
    data_atualizacao
```

Não implementar ainda todo o módulo de compras.

Apenas deixar a estrutura preparada para entrada de mercadorias.

---

# 23. Inventário

Criar conceito separado de inventário físico.

O inventário deve permitir:

1. iniciar inventário;
2. selecionar produtos;
3. informar quantidade física;
4. comparar quantidade esperada;
5. calcular divergência;
6. revisar;
7. finalizar;
8. gerar ajustes de estoque.

Criar algo semelhante a:

```
Inventario
    uuid
    tenant
    descricao
    status
    data_inicio
    data_finalizacao
    usuario_criacao
    usuario_finalizacao
```

E:

```
InventarioItem
    uuid
    inventario
    produto
    quantidade_sistema
    quantidade_contada
    diferenca
```

---

# 24. Regra do inventário

Ao iniciar o inventário, armazenar a quantidade do sistema utilizada como referência.

Não depender exclusivamente do saldo atual posteriormente.

Exemplo:

```
quantidade_sistema = 100
```

durante a contagem alguém vende 10 unidades.

O inventário ainda deve conseguir determinar corretamente a divergência de acordo com a regra definida para o processo.

Documentar claramente a estratégia utilizada.

Ao finalizar o inventário, gerar movimentações de ajuste.

Nunca simplesmente sobrescrever o estoque sem histórico.

---

# 25. Status do inventário

Utilizar estados explícitos:

```
ABERTO
EM_CONTAGEM
EM_REVISAO
FINALIZADO
CANCELADO
```

Não permitir alterações arbitrárias depois de finalizado.

---

# 26. Auditoria

Operações importantes devem registrar:

* usuário;
* tenant;
* data/hora;
* operação;
* produto;
* quantidade anterior;
* quantidade posterior;
* motivo.

Especialmente:

* criação;
* alteração;
* desativação;
* entrada;
* saída;
* ajuste;
* inventário;
* alteração de preço.

---

# 27. Exclusão de produtos

Evitar `DELETE` físico para produtos que já possuam:

* vendas;
* movimentações;
* inventários;
* histórico.

Preferir:

```
ativo = False
```

ou mecanismo de soft delete já existente no projeto.

Produtos utilizados em documentos fiscais nunca devem simplesmente desaparecer do banco.

---

# 28. Pesquisa de produtos

Criar uma tela de listagem com:

* nome;
* SKU;
* código de barras;
* categoria;
* marca;
* status;
* estoque;
* preço;
* data de cadastro.

Permitir busca por:

* nome;
* SKU;
* código de barras.

Permitir filtros por:

* categoria;
* marca;
* ativo/inativo;
* estoque baixo;
* sem estoque.

Implementar paginação.

Não carregar milhares de produtos de uma vez no HTML.

---

# 29. Interface

Criar interface utilizando:

* Django Templates;
* TailwindCSS;
* HTML semântico;
* JavaScript vanilla.

Não introduzir SPA.

A interface deve possuir:

## Produtos

```
/produtos/
/produtos/novo/
/produtos/<uuid>/
/produtos/<uuid>/editar/
```

## Estoque

```
/estoque/
/estoque/entrada/
/estoque/saida/
/estoque/movimentacoes/
```

## Inventário

```
/inventarios/
/inventarios/novo/
/inventarios/<uuid>/
/inventarios/<uuid>/contagem/
/inventarios/<uuid>/finalizar/
```

Adaptar as URLs aos padrões existentes do projeto.

---

# 30. Tela de cadastro

A tela de produto deve permitir:

* nome;
* SKU;
* categoria;
* marca;
* tamanho;
* unidade;
* custo;
* preço de venda;
* estoque mínimo;
* estoque máximo;
* código de barras;
* observação;
* ativo.

O código de barras deve possuir opção:

```
Gerar código
```

O usuário também poderá informar manualmente um código quando isso fizer sentido para produtos que já possuem código de barras.

Validar unicidade dentro do tenant.

---

# 31. Leitor de código de barras

Preparar a interface para uso com leitores USB de código de barras.

A maioria desses leitores funciona como teclado HID.

O sistema deve permitir que o campo de busca aceite a sequência:

```
7891234567890
```

e localize o produto.

Não depender inicialmente de câmera para leitura.

A integração com câmera pode ser implementada futuramente.

---

# 32. Integração futura com PDV

O módulo deve ser preparado para o PDV.

O PDV deverá conseguir consultar um produto por:

```
UUID
SKU
código de barras
```

Criar serviços/API interna adequados para isso, sem acoplar a lógica de estoque diretamente à interface do PDV.

Uma venda futura deverá chamar:

```
EstoqueService.registrar_venda(...)
```

em vez de alterar o estoque diretamente.

---

# 33. Preparação para módulo fiscal

O cadastro de produto deverá ser preparado para futura emissão de NF-e/NFC-e.

Avaliar campos fiscais que serão necessários futuramente, como:

* NCM;
* CEST;
* origem da mercadoria;
* CFOP;
* CST;
* CSOSN;
* unidade tributável;
* código de benefício fiscal quando aplicável.

IMPORTANTE:

Não inventar valores fiscais.

Se esses campos forem implementados agora, devem possuir validações e documentação apropriadas.

Se o módulo fiscal ainda não estiver sendo implementado, pode ser melhor criar uma estrutura fiscal separada para não poluir o model principal de produto.

A decisão deve ser justificada antes da implementação.

---

# 34. Banco de dados

Criar índices para consultas frequentes.

Especialmente:

* tenant + UUID;
* tenant + SKU;
* tenant + código de barras;
* tenant + nome;
* tenant + ativo.

As constraints de unicidade devem considerar o tenant quando apropriado.

Exemplo conceitual:

```
UniqueConstraint(
    fields=["tenant", "sku"],
    name="unique_product_sku_per_tenant"
)
```

e:

```
UniqueConstraint(
    fields=["tenant", "codigo_barras"],
    name="unique_barcode_per_tenant"
)
```

Não assumir que `unique=True` no campo SKU ou código de barras seja adequado para multi-tenancy.

---

# 35. Performance

Evitar N+1 queries.

Utilizar adequadamente:

```
select_related()
prefetch_related()
```

quando necessário.

Paginar listagens.

Não calcular estoque fazendo `SUM()` de todas as movimentações em cada requisição.

O saldo atual deve ser obtido de uma estrutura adequada, mantendo as movimentações como histórico/auditoria.

---

# 36. Services

Separar regras de negócio dos templates/views.

Criar, quando apropriado:

```
ProductService
BarcodeService
EstoqueService
InventarioService
```

As views devem orquestrar a requisição.

As regras de negócio devem permanecer nos services/domínio.

---

# 37. Validações

Implementar validações no backend.

Exemplos:

* nome obrigatório;
* preço não negativo;
* custo não negativo;
* quantidade positiva;
* SKU válido;
* código de barras válido;
* tamanho dentro do limite definido;
* categoria pertencente ao tenant;
* fornecedor pertencente ao tenant;
* produto pertencente ao tenant.

Não confiar apenas na validação HTML/JavaScript.

---

# 38. CSRF e segurança

Todas as operações de alteração via POST devem possuir proteção CSRF.

Não permitir alteração através de GET.

Operações destrutivas devem exigir confirmação.

Respeitar autenticação e autorização existentes.

Usuários sem permissão não devem conseguir alterar estoque.

---

# 39. Permissões

Preparar permissões específicas, por exemplo:

```
products.view_product
products.add_product
products.change_product
products.delete_product

inventory.view_stock
inventory.change_stock
inventory.create_movement
inventory.create_inventory
inventory.finalize_inventory
```

Adaptar ao sistema de permissões já existente.

Não criar um sistema paralelo se o projeto já possuir RBAC/permissões.

---

# 40. Testes

Criar testes unitários e de integração.

Obrigatoriamente testar:

## Multi-tenancy

* tenant A não consegue acessar produto do tenant B;
* tenant A não consegue alterar produto do tenant B;
* tenant A não consegue consultar estoque do tenant B;
* tenant A não consegue criar movimentação para produto do tenant B;
* códigos de barras podem existir em tenants diferentes;
* SKU pode existir em tenants diferentes.

## Produto

* criação;
* alteração;
* desativação;
* validação;
* UUID automático.

## Código de barras

* geração;
* dígito verificador;
* unicidade;
* validação;
* renderização.

## Estoque

* entrada;
* saída;
* ajuste;
* venda;
* devolução;
* estoque negativo;
* concorrência;
* rollback transacional.

## Inventário

* criação;
* contagem;
* divergência;
* finalização;
* geração de ajustes;
* cancelamento;
* bloqueio após finalização.

---

# 41. Concorrência — teste obrigatório

Criar teste que simule duas operações simultâneas.

Exemplo:

Estoque:

```
10
```

Duas vendas simultâneas:

```
7
7
```

Se estoque negativo estiver desabilitado, somente uma operação poderá consumir o estoque disponível.

O resultado final não pode ser:

```
-4
```

nem:

```
3
```

sem que a segunda operação tenha sido corretamente rejeitada.

---

# 42. Integridade

O sistema deve sempre conseguir responder:

> "Como este produto chegou ao estoque atual?"

A resposta deve estar disponível através das movimentações.

Exemplo:

```
Estoque inicial: 0

+50 ENTRADA
-3 VENDA
-2 VENDA
+1 DEVOLUÇÃO
-4 AJUSTE

Saldo atual: 42
```

O saldo deve ser auditável.

---

# 43. API interna/futura

Mesmo utilizando Django Templates, estruturar os services de forma que futuramente possam ser expostos através de API.

Não implementar Django REST Framework sem necessidade.

Não criar API apenas por criar.

O objetivo é manter a camada de domínio independente da interface.

---

# 44. UX

A interface deve deixar claro:

* estoque atual;
* estoque mínimo;
* estoque máximo;
* situação do estoque.

Exemplos:

```
Em estoque
Estoque baixo
Sem estoque
```

Utilizar indicadores visuais, mas não depender apenas de cores.

---

# 45. Dashboard de estoque

Criar uma página inicial do módulo de estoque mostrando:

* total de produtos;
* produtos ativos;
* produtos sem estoque;
* produtos com estoque baixo;
* valor estimado do estoque pelo custo;
* valor estimado do estoque pelo preço de venda;
* últimas movimentações;
* últimos produtos cadastrados.

Os cálculos devem ser eficientes.

---

# 46. Histórico do produto

Cada produto deverá possuir uma página detalhada mostrando:

* dados cadastrais;
* código de barras;
* SKU;
* preço;
* estoque atual;
* estoque mínimo/máximo;
* movimentações;
* inventários relacionados;
* alterações relevantes.

---

# 47. Importação futura

Preparar arquitetura para futura importação de produtos via:

* CSV;
* Excel;
* integração com fornecedores.

Não implementar agora, a menos que o projeto já possua infraestrutura para isso.

---

# 48. Exportação

Preparar estrutura para futura exportação de:

* produtos;
* estoque;
* movimentações;
* inventários.

Não implementar agora se estiver fora do escopo.

---

# 49. Ordem de implementação

Não implementar tudo simultaneamente.

Dividir em fases.

## Fase 1 — Análise

Antes de escrever código:

1. analisar estrutura do projeto;
2. identificar tenancy;
3. identificar autenticação;
4. identificar usuários;
5. identificar padrões de models;
6. identificar sistema de permissões;
7. identificar layout/base templates;
8. identificar configuração Tailwind;
9. identificar padrões de URLs;
10. identificar banco de dados.

Produzir um plano antes de modificar o código.

---

## Fase 2 — Produtos

Implementar:

* Product;
* Categoria;
* Marca, se necessária;
* SKU;
* UUID;
* código de barras;
* preços;
* cadastro;
* edição;
* listagem;
* pesquisa;
* filtros.

---

## Fase 3 — Barcode

Implementar:

* geração EAN-13 interno;
* validação;
* dígito verificador;
* renderização;
* impressão futura.

---

## Fase 4 — Estoque

Implementar:

* estoque;
* movimentações;
* entrada;
* saída;
* ajustes;
* regras de estoque negativo;
* concorrência;
* auditoria.

---

## Fase 5 — Inventário

Implementar:

* inventário;
* itens;
* contagem;
* divergência;
* revisão;
* finalização;
* ajustes automáticos.

---

## Fase 6 — Interface

Construir:

* dashboard;
* produtos;
* cadastro;
* edição;
* detalhes;
* estoque;
* movimentações;
* inventários.

---

## Fase 7 — Integração com PDV

Preparar:

* busca por código de barras;
* busca por SKU;
* consulta de preço;
* baixa de estoque;
* devolução.

---

# 50. Critérios de aceite

O módulo somente será considerado concluído quando:

### Produto

For possível criar um produto contendo:

```
UUID
nome
data de cadastro
tamanho
observação
SKU
preço
estoque
```

### Código de barras

For possível:

```
gerar código de barras
validar código
visualizar código
localizar produto pelo código
```

### Estoque

For possível:

```
adicionar estoque
retirar estoque
ajustar estoque
visualizar saldo
visualizar histórico
```

### Inventário

For possível:

```
criar inventário
contar produtos
visualizar divergências
revisar
finalizar
gerar ajustes
```

### Multi-tenancy

For impossível:

```
tenant A → acessar dados → tenant B
```

inclusive através de:

* URL;
* UUID;
* SKU;
* código de barras;
* POST manual;
* manipulação de parâmetros;
* chamadas concorrentes.

### Integridade

Toda alteração de estoque deverá possuir histórico.

Não deve existir alteração silenciosa de saldo.

---

# 51. Regra final para o agent

Antes de modificar qualquer arquivo:

1. leia a arquitetura existente;
2. identifique como multi-tenancy está implementado;
3. identifique os models existentes;
4. identifique os padrões de autenticação/autorização;
5. identifique o layout frontend;
6. identifique como Tailwind está configurado;
7. produza um plano;
8. aguarde a validação do plano antes de implementar a primeira fase.

Não reescreva componentes existentes sem necessidade.

Não crie um novo sistema de autenticação.

Não crie um novo sistema de tenancy.

Não crie um novo sistema de permissões.

Não introduza dependências desnecessárias.

Não implemente regras fiscais por suposição.

Não use `float` para dinheiro.

Não faça alterações diretas de estoque fora do `EstoqueService`.

Não permita acesso cross-tenant.

Priorize:

```
segurança
integridade dos dados
auditabilidade
consistência transacional
simplicidade
extensibilidade
```

O módulo deverá estar preparado para posteriormente integrar:

```
PDV
NFC-e
NF-e
compras
fornecedores
relatórios
impressão de etiquetas
leitores de código de barras
```

sem precisar ser reescrito.


# Implementação do Módulo Financeiro

Você é responsável por implementar o módulo financeiro de um sistema de gestão/PDV.

O sistema utiliza:

* Python
* Django
* Django Templates
* HTML
* JavaScript
* CSS
* TailwindCSS
* Banco de dados relacional

A aplicação é **multi-tenant**.

O módulo financeiro deverá ser dividido inicialmente em quatro grandes áreas:

1. Entrada
2. Saída
3. Valores a receber
4. Análise financeira por período

A arquitetura deve ser preparada para futuras integrações com:

* PDV;
* vendas;
* NFC-e;
* NF-e;
* compras;
* fornecedores;
* clientes;
* contas bancárias;
* cartões;
* PIX;
* boletos;
* fluxo de caixa.

---

# 1. Regra fundamental — Multi-tenancy

O sistema é multi-tenant.

Todo dado financeiro deve obrigatoriamente pertencer a um tenant.

Isso inclui:

* entradas;
* saídas;
* contas a receber;
* categorias;
* contas financeiras;
* formas de pagamento;
* centros de custo;
* lançamentos;
* pagamentos;
* análises;
* relatórios.

Um tenant jamais poderá acessar dados financeiros de outro tenant.

Não confiar em:

* UUID;
* ID;
* URL;
* parâmetros GET;
* POST;
* JavaScript.

O backend deve sempre determinar o tenant através do mecanismo de tenancy já existente.

Antes de implementar:

1. identificar o sistema atual de tenancy;
2. identificar como o tenant é obtido;
3. identificar como usuários pertencem ao tenant;
4. identificar o padrão utilizado pelos demais módulos;
5. reutilizar a implementação existente.

NÃO criar um segundo sistema de tenancy.

---

# 2. Princípios financeiros

O módulo deve diferenciar claramente:

## Lançamento

Representa uma obrigação ou movimentação financeira.

Exemplo:

```
Compra de mercadorias
R$ 1.000,00
vencimento: 20/09/2026
```

## Pagamento/recebimento

Representa o momento em que o dinheiro efetivamente entrou ou saiu.

Isso é importante porque:

```
competência ≠ caixa
```

Exemplo:

```
Venda em 10/09
Vencimento em 10/10
Recebimento em 10/10
```

O lançamento pertence ao período de competência da operação.

O fluxo de caixa considera o recebimento efetivo.

Não misturar esses conceitos.

---

# 3. Estrutura geral

Criar uma arquitetura semelhante a:

```
financial/
    models/
    services/
    repositories/
    forms/
    views/
    urls/
    templates/
    templatetags/
    selectors/
    reports/
    domain/
    tests/
```

Adaptar à arquitetura já existente.

Não criar estrutura paralela desnecessariamente.

---

# 4. Entidades principais

Avaliar a criação das seguintes entidades:

```
CategoriaFinanceira
ContaFinanceira
Entrada
Saida
ContaReceber
Recebimento
CentroCusto
FormaPagamento
```

A arquitetura deve evitar duplicação desnecessária.

---

# 5. UUID

Todas as entidades financeiras importantes deverão possuir:

```
uuid
```

gerado no backend através de UUID.

Exemplo conceitual:

```
uuid = UUIDField(
    default=uuid.uuid4,
    editable=False,
    unique=True
)
```

O UUID é um identificador técnico.

Não utilizar UUID como identificador financeiro exibido ao usuário.

---

# 6. Valores monetários

Nunca utilizar:

```
float
```

para dinheiro.

Utilizar:

```
DecimalField
```

com precisão apropriada.

Exemplo:

```
max_digits=14
decimal_places=2
```

Todos os cálculos financeiros devem utilizar Decimal.

Não realizar operações monetárias utilizando float em JavaScript e depois enviar o resultado como verdade para o backend.

O backend é a autoridade para cálculos financeiros.

---

# 7. Categorias financeiras

Criar categorias financeiras.

Exemplos de entrada:

```
Venda
Recebimento
Outros
```

Exemplos de saída:

```
Fornecedor
Salários
Aluguel
Energia
Internet
Impostos
Manutenção
Marketing
Outros
```

Model conceitual:

```
CategoriaFinanceira
    uuid
    tenant
    nome
    tipo
    descricao
    ativo
    data_cadastro
    data_atualizacao
```

Onde tipo pode ser:

```
ENTRADA
SAIDA
AMBOS
```

A categoria deve pertencer ao tenant.

---

# 8. Subcategorias

Avaliar suporte a hierarquia.

Exemplo:

```
Despesas
    Operacionais
        Energia
        Internet
        Aluguel
```

Não implementar uma árvore excessivamente complexa se o sistema atual não precisar disso.

Uma estrutura simples de categoria pai pode ser suficiente.

---

# 9. Conta financeira

Criar estrutura para representar onde o dinheiro está.

Exemplos:

```
Caixa
Banco Itaú
Banco do Brasil
Nubank
Conta PIX
Carteira
```

Model conceitual:

```
ContaFinanceira
    uuid
    tenant
    nome
    tipo
    saldo_inicial
    data_saldo_inicial
    ativo
    data_cadastro
```

Tipos:

```
CAIXA
CONTA_BANCARIA
CARTEIRA
PIX
OUTRO
```

Não assumir que uma conta financeira representa necessariamente uma conta bancária.

---

# 10. Entradas

A primeira parte do módulo será o cadastro de entradas.

Uma entrada representa dinheiro ou receita que entra no negócio.

Exemplo:

```
Venda
R$ 500,00
Categoria: Venda
Conta: Caixa
Data: 20/08/2026
```

Model conceitual:

```
Entrada
    uuid
    tenant
    descricao
    valor
    categoria
    conta_financeira
    data_competencia
    data_pagamento
    status
    observacao
    usuario_criacao
    data_criacao
    data_atualizacao
```

Avaliar integração posterior com vendas do PDV.

---

# 11. Status da entrada

Utilizar estados explícitos.

Exemplo:

```
PREVISTA
PENDENTE
RECEBIDA
CANCELADA
```

Uma entrada prevista não deve alterar o saldo da conta financeira.

Uma entrada recebida deve afetar o fluxo de caixa.

---

# 12. Registro de entrada

Criar formulário para:

* descrição;
* valor;
* categoria;
* conta financeira;
* data de competência;
* data prevista;
* data de recebimento;
* observação.

O formulário deve permitir:

```
Salvar como pendente
```

ou:

```
Registrar como recebido
```

Quando registrada como recebida:

1. criar entrada;
2. registrar recebimento;
3. atualizar conta financeira;
4. registrar histórico.

Tudo dentro de uma transação.

---

# 13. Saídas

A segunda parte será o cadastro de saídas.

Exemplos:

```
aluguel
fornecedor
energia
telefone
salário
imposto
manutenção
```

Model conceitual:

```
Saida
    uuid
    tenant
    descricao
    valor
    categoria
    conta_financeira
    data_competencia
    data_vencimento
    data_pagamento
    status
    observacao
    usuario_criacao
    data_criacao
    data_atualizacao
```

---

# 14. Status da saída

Utilizar:

```
PREVISTA
PENDENTE
PAGA
ATRASADA
CANCELADA
```

Uma saída pendente não altera o saldo da conta.

Uma saída paga reduz o saldo.

Uma saída vencida deve ser identificada automaticamente.

---

# 15. Pagamento de saída

Ao pagar uma saída:

1. validar conta financeira;
2. validar valor;
3. verificar saldo quando aplicável;
4. registrar data de pagamento;
5. atualizar status;
6. registrar movimentação financeira;
7. atualizar saldo;
8. salvar histórico.

Utilizar transação atômica.

---

# 16. Valores a receber

A terceira parte será o módulo de contas a receber.

Esse módulo NÃO deve ser simplesmente uma lista de entradas.

Ele deve representar valores que a empresa possui direito de receber.

Exemplo:

```
Cliente:
    João

Venda:
    R$ 1.000

Forma:
    3 parcelas

Parcelas:

    333,33 — 10/09
    333,33 — 10/10
    333,34 — 10/11
```

Criar:

```
ContaReceber
```

e:

```
ParcelaReceber
```

quando necessário.

---

# 17. ContaReceber

Estrutura conceitual:

```
ContaReceber
    uuid
    tenant
    cliente
    descricao
    valor_total
    data_competencia
    origem
    referencia
    status
    observacao
    data_criacao
```

A origem poderá futuramente ser:

```
VENDA
MANUAL
OUTRO
```

A referência poderá armazenar a identificação da entidade de origem.

Preferir uma arquitetura preparada para ForeignKey futura em vez de armazenar apenas texto.

---

# 18. Parcelas

Criar suporte a parcelamento.

Estrutura:

```
ParcelaReceber
    uuid
    tenant
    conta_receber
    numero
    valor
    data_vencimento
    data_recebimento
    status
    conta_financeira
    observacao
```

Status:

```
PENDENTE
RECEBIDA
ATRASADA
CANCELADA
```

Cada parcela deve possuir seu próprio vencimento.

---

# 19. Divisão correta de valores

Ao parcelar:

```
valor_total = 100,00
```

em:

```
3 parcelas
```

não permitir erro de arredondamento.

O sistema deve produzir algo como:

```
33,33
33,33
33,34
```

Total:

```
100,00
```

O backend deve ser responsável por essa divisão.

Criar testes específicos.

---

# 20. Recebimento

Ao receber uma parcela:

1. validar parcela;
2. verificar tenant;
3. verificar status;
4. definir conta financeira;
5. definir data;
6. registrar recebimento;
7. atualizar saldo;
8. atualizar status;
9. registrar histórico.

Tudo dentro de `transaction.atomic()`.

---

# 21. Estorno

Preparar arquitetura para estornos.

Não apagar um recebimento que já ocorreu.

Exemplo:

```
RECEBIMENTO
    + R$ 500
```

Depois:

```
ESTORNO
    - R$ 500
```

Isso mantém a auditoria.

O mesmo princípio deverá ser aplicado às saídas.

---

# 22. Movimentação financeira

Recomenda-se criar uma entidade central:

```
MovimentacaoFinanceira
```

Exemplo:

```
MovimentacaoFinanceira
    uuid
    tenant
    conta_financeira
    tipo
    valor
    data
    origem
    referencia
    descricao
    usuario
    data_criacao
```

Tipos:

```
ENTRADA
SAIDA
ESTORNO_ENTRADA
ESTORNO_SAIDA
```

Essa entidade representa o movimento efetivo do caixa/conta.

Isso permite posteriormente calcular o saldo de forma auditável.

---

# 23. Saldo

O saldo de uma conta financeira não deve ser alterado arbitrariamente.

Uma alteração deve sempre possuir uma movimentação correspondente.

Exemplo:

```
Saldo inicial:
R$ 1.000

+ R$ 500 venda
- R$ 200 despesa
+ R$ 300 recebimento

Saldo:
R$ 1.600
```

Criar serviço:

```
FinancialService
```

ou:

```
AccountService
```

responsável pelas movimentações.

---

# 24. Concorrência

Considerar operações simultâneas.

Exemplo:

```
Saldo:
R$ 1.000
```

Duas saídas simultâneas:

```
R$ 700
R$ 700
```

O sistema não pode permitir que ambas sejam processadas incorretamente se a conta não permitir saldo negativo.

Utilizar mecanismos apropriados do banco:

```
select_for_update()
```

quando necessário.

---

# 25. Saldo negativo

Criar configuração por conta financeira:

```
permitir_saldo_negativo
```

Se falso:

```
saldo = 100
saída = 150
```

deve resultar em erro.

Se verdadeiro:

```
saldo = -50
```

pode ser permitido.

A regra deve ser definida no backend.

---

# 26. Formas de pagamento

Criar estrutura preparada para:

```
DINHEIRO
PIX
DEBITO
CREDITO
BOLETO
TRANSFERENCIA
OUTRO
```

Não confundir:

```
forma de pagamento
```

com:

```
conta financeira
```

Exemplo:

```
Forma:
PIX

Conta:
Banco Itaú
```

---

# 27. Taxas

Preparar arquitetura para taxas.

Especialmente cartões:

```
valor bruto:
R$ 100

taxa:
R$ 3

valor líquido:
R$ 97
```

Não implementar regras complexas de adquirentes inicialmente.

Mas deixar o domínio preparado para:

```
valor_bruto
taxa
valor_liquido
```

---

# 28. Análise financeira por período

A quarta parte do módulo será uma tela de análise financeira.

O usuário deverá conseguir selecionar:

```
data inicial
data final
```

E analisar:

* entradas;
* saídas;
* saldo;
* contas a receber;
* valores vencidos;
* valores a vencer;
* resultado do período;
* fluxo de caixa.

---

# 29. Indicadores

A tela deve apresentar cards como:

```
Total de entradas
Total de saídas
Resultado
A receber
Vencido
A vencer
```

Exemplo:

```
Entradas:
R$ 25.000

Saídas:
R$ 18.000

Resultado:
R$ 7.000
```

---

# 30. Resultado

Calcular:

```
resultado = entradas - saídas
```

Utilizar somente valores efetivamente recebidos/pagos quando o relatório estiver em modo:

```
CAIXA
```

---

# 31. Competência

Preparar também modo:

```
COMPETENCIA
```

Nesse caso:

* receitas entram pela data de competência;
* despesas entram pela data de competência;
* pagamentos não alteram a competência.

O relatório deve permitir futuramente alternar:

```
Caixa
Competência
```

Não misturar os dois conceitos.

---

# 32. Fluxo de caixa

Criar visualização temporal.

Exemplo:

```
Data       Entradas       Saídas       Resultado

20/08      1.000          500          +500
21/08      2.000          700          +1.300
22/08      500            900          -400
```

Permitir agrupamento por:

```
dia
semana
mês
```

---

# 33. Análise por categoria

Exibir:

```
Entradas por categoria
```

e:

```
Saídas por categoria
```

Exemplo:

```
Vendas             R$ 20.000
Serviços           R$ 3.000
Outros             R$ 500
```

Saídas:

```
Fornecedores       R$ 10.000
Salários           R$ 5.000
Aluguel            R$ 2.000
Impostos           R$ 1.000
```

---

# 34. Análise por conta

Permitir visualizar:

```
Caixa
Banco
PIX
```

com respectivos saldos e movimentações.

---

# 35. Valores vencidos

A análise deverá destacar:

```
contas vencidas
```

sem recebimento/pagamento.

Exemplo:

```
R$ 4.500 vencidos
```

Permitir clicar e visualizar os lançamentos.

---

# 36. Valores a vencer

Exibir:

```
hoje
próximos 7 dias
próximos 30 dias
período selecionado
```

---

# 37. Dashboard

Criar uma dashboard financeira responsiva.

Utilizar TailwindCSS.

A dashboard deverá apresentar:

* cards;
* tabelas;
* filtros;
* indicadores;
* gráficos quando realmente úteis.

Não transformar a página em um painel visual excessivamente complexo.

Priorizar legibilidade.

---

# 38. Gráficos

Se forem utilizados gráficos:

* utilizar biblioteca somente se já existir no projeto;
* caso contrário, avaliar uma solução simples;
* não adicionar dependência pesada sem necessidade.

Gráficos desejáveis:

## Entradas x Saídas

Visualização temporal.

## Despesas por categoria

Distribuição das despesas.

## Receitas por categoria

Distribuição das receitas.

## Fluxo acumulado

Evolução do caixa.

Todos os dados dos gráficos devem ser calculados pelo backend.

JavaScript apenas renderiza.

---

# 39. Filtros

A análise deverá possuir:

```
período

categoria

conta

tipo

status

forma de pagamento
```

Os filtros devem ser aplicados no backend.

Não carregar todo o banco para filtrar no JavaScript.

---

# 40. Períodos rápidos

Adicionar opções:

```
Hoje
Ontem
Últimos 7 dias
Últimos 30 dias
Este mês
Mês anterior
Este ano
Personalizado
```

O cálculo das datas deve ser feito de forma timezone-aware.

---

# 41. Interface de entradas

Criar:

```
/financeiro/entradas/
```

Com:

* listagem;
* busca;
* filtros;
* paginação;
* criação;
* edição;
* visualização;
* cancelamento;
* registro de recebimento.

---

# 42. Interface de saídas

Criar:

```
/financeiro/saidas/
```

Com:

* listagem;
* busca;
* filtros;
* paginação;
* criação;
* edição;
* visualização;
* cancelamento;
* registro de pagamento.

---

# 43. Interface de contas a receber

Criar:

```
/financeiro/receber/
```

Com:

* contas pendentes;
* vencidas;
* recebidas;
* canceladas;
* filtros;
* pesquisa;
* parcelamento;
* recebimento.

---

# 44. Interface de análise

Criar:

```
/financeiro/analise/
```

Com:

* período;
* cards;
* entradas;
* saídas;
* resultado;
* fluxo;
* categorias;
* contas;
* valores vencidos;
* valores a vencer.

---

# 45. Permissões

Utilizar o sistema de permissões existente.

Criar permissões quando necessário:

```
financial.view_entry
financial.add_entry
financial.change_entry
financial.cancel_entry

financial.view_expense
financial.add_expense
financial.change_expense
financial.cancel_expense

financial.view_receivable
financial.receive_receivable

financial.view_analysis
```

Adaptar ao padrão já existente.

Não criar sistema de autorização paralelo.

---

# 46. Auditoria

Registrar:

* usuário;
* tenant;
* data/hora;
* ação;
* entidade;
* valor anterior;
* valor posterior;
* motivo.

Especialmente:

* criação;
* alteração;
* pagamento;
* recebimento;
* cancelamento;
* estorno;
* alteração de categoria;
* alteração de conta.

Não excluir silenciosamente lançamentos financeiros importantes.

---

# 47. Cancelamento

Não apagar lançamentos que já tenham impacto financeiro.

Utilizar cancelamento lógico.

Quando uma movimentação já ocorreu, utilizar estorno quando necessário.

Manter histórico.

---

# 48. Integração com PDV

Preparar o módulo para que uma venda futura possa gerar automaticamente:

```
Venda
  ↓
ContaReceber
  ↓
Parcelas
  ↓
Recebimento
  ↓
MovimentacaoFinanceira
```

O módulo financeiro não deve depender da tela do PDV.

O PDV deverá utilizar services.

---

# 49. Integração futura com estoque

Uma compra futura poderá gerar:

```
Compra
  ↓
Entrada de estoque
  +
Conta a pagar
```

Não implementar contas a pagar como módulo completo nesta etapa, mas deixar a arquitetura preparada.

---

# 50. Conta a pagar

IMPORTANTE:

Embora a primeira versão esteja focada em:

```
Entrada
Saída
Contas a receber
Análise
```

A arquitetura deve permitir posteriormente criar:

```
ContaAPagar
```

sem precisar reestruturar todo o financeiro.

Evitar que `Saida` seja projetada de maneira que impeça esse futuro módulo.

---

# 51. Serviços

Criar serviços de domínio apropriados.

Exemplo:

```
EntryService
ExpenseService
ReceivableService
FinancialAccountService
FinancialAnalysisService
FinancialMovementService
```

As views não devem conter regras financeiras complexas.

---

# 52. Transações

Operações financeiras devem utilizar:

```
transaction.atomic()
```

Especialmente:

* recebimento;
* pagamento;
* estorno;
* alteração de saldo;
* criação de movimentação.

Uma operação deve ser completamente concluída ou completamente revertida.

---

# 53. Precisão

Nunca utilizar:

```
float
```

para cálculos financeiros.

Utilizar:

```
Decimal
```

no backend.

No frontend:

* formatar valores para BRL;
* não assumir que o valor exibido é o valor financeiro definitivo;
* enviar dados de maneira segura;
* deixar o backend validar e calcular.

---

# 54. Performance

Consultas financeiras podem crescer rapidamente.

Portanto:

* criar índices adequados;
* filtrar por tenant;
* filtrar por datas;
* utilizar agregações SQL;
* evitar carregar milhares de registros em Python;
* evitar N+1 queries;
* utilizar `select_related`;
* utilizar `prefetch_related` quando apropriado.

A análise financeira deve ser calculada no banco sempre que possível.

---

# 55. Índices

Avaliar índices para:

```
tenant
data_competencia
data_vencimento
data_pagamento
status
categoria
conta_financeira
```

Para consultas multi-tenant, considerar índices compostos como:

```
tenant + data
tenant + status
tenant + categoria
```

---

# 56. Relatórios

Preparar a camada para futuramente permitir:

* PDF;
* CSV;
* Excel.

Não implementar todos agora se não estiverem no escopo.

A camada de análise não deve depender da interface HTML.

---

# 57. Testes

Criar testes obrigatórios para:

## Multi-tenancy

* tenant A não acessa tenant B;
* tenant A não altera tenant B;
* tenant A não recebe valor pertencente a tenant B;
* categorias isoladas;
* contas financeiras isoladas.

## Valores

* Decimal;
* arredondamento;
* parcelamento;
* soma das parcelas;
* taxas;
* valor líquido.

## Entrada

* criação;
* recebimento;
* cancelamento;
* estorno.

## Saída

* criação;
* pagamento;
* cancelamento;
* estorno;
* saldo insuficiente.

## Contas a receber

* criação;
* parcelas;
* vencimento;
* atraso;
* recebimento;
* cancelamento.

## Análise

* período;
* entradas;
* saídas;
* resultado;
* categorias;
* contas;
* fluxo de caixa.

---

# 58. Teste de isolamento

Criar explicitamente testes como:

```
Tenant A
    Entrada = R$ 1.000

Tenant B
    Entrada = R$ 5.000
```

A análise financeira do Tenant A deve retornar:

```
R$ 1.000
```

e jamais:

```
R$ 6.000
```

O mesmo deve ser testado para:

* saídas;
* contas;
* recebíveis;
* categorias;
* movimentações.

---

# 59. Teste de concorrência

Criar testes para operações simultâneas sobre uma conta financeira.

Exemplo:

```
saldo = R$ 1.000
```

Duas operações simultâneas:

```
- R$ 700
- R$ 700
```

Se saldo negativo não for permitido, apenas uma deve ser concluída.

Não pode haver inconsistência entre:

```
saldo
movimentações
```

---

# 60. Ordem de implementação

Não implementar tudo de uma vez.

## Fase 1 — Análise

Antes de escrever código:

1. analisar arquitetura;
2. analisar tenancy;
3. analisar autenticação;
4. analisar permissões;
5. analisar models existentes;
6. analisar usuários;
7. analisar clientes;
8. analisar fornecedores;
9. analisar vendas, se já existirem;
10. analisar layout;
11. analisar Tailwind;
12. analisar banco.

Depois apresentar um plano.

---

# 61. Fase 2 — Base financeira

Implementar:

* categorias;
* contas financeiras;
* formas de pagamento;
* estrutura de movimentações;
* permissões;
* auditoria.

---

# 62. Fase 3 — Entradas

Implementar:

* cadastro;
* edição;
* recebimento;
* cancelamento;
* histórico;
* movimentação financeira.

---

# 63. Fase 4 — Saídas

Implementar:

* cadastro;
* pagamento;
* cancelamento;
* estorno;
* histórico;
* movimentação.

---

# 64. Fase 5 — Contas a receber

Implementar:

* conta;
* parcelas;
* vencimentos;
* atraso;
* recebimento;
* estorno.

---

# 65. Fase 6 — Análise

Implementar:

* filtros;
* período;
* cards;
* fluxo;
* categorias;
* contas;
* vencidos;
* a vencer.

---

# 66. Fase 7 — Integrações

Preparar integração com:

```
PDV
vendas
clientes
fornecedores
NFC-e
estoque
```

---

# 67. Regra de ouro

Nunca modificar diretamente um saldo sem registrar a movimentação correspondente.

Nunca excluir silenciosamente uma operação financeira que já ocorreu.

Nunca permitir acesso cross-tenant.

Nunca usar float para dinheiro.

Nunca confiar em valores financeiros enviados pelo frontend.

Nunca colocar regra financeira complexa dentro de uma view.

Nunca considerar uma operação concluída apenas porque o banco salvou um registro principal.

Uma operação financeira deverá sempre preservar:

```
lançamento
movimentação
saldo
histórico
auditoria
```

de maneira consistente.

---

# 68. Critérios de aceite

O módulo será considerado funcional quando for possível:

### Entrada

Criar uma entrada:

```
R$ 1.000
categoria: Venda
conta: Caixa
```

Registrar o recebimento.

O saldo do Caixa deverá aumentar em:

```
R$ 1.000
```

---

### Saída

Criar uma saída:

```
R$ 300
categoria: Energia
conta: Caixa
```

Registrar pagamento.

O saldo deverá diminuir em:

```
R$ 300
```

---

### Conta a receber

Criar:

```
R$ 1.200
```

em 3 parcelas:

```
R$ 400
R$ 400
R$ 400
```

Registrar o recebimento da segunda parcela.

O sistema deverá mostrar:

```
Recebido: R$ 400
Pendente: R$ 800
```

---

### Análise

Selecionar:

```
01/08/2026
até
31/08/2026
```

O sistema deverá mostrar:

```
Entradas
Saídas
Resultado
Recebimentos pendentes
Recebimentos vencidos
Fluxo de caixa
```

---

### Multi-tenancy

Tenant A jamais poderá visualizar ou alterar qualquer dado financeiro do Tenant B.

Isso deverá ser comprovado através de testes automatizados.

---

# 69. Regra final para o agent

Antes de escrever código:

1. leia o projeto;
2. identifique a implementação atual de multi-tenancy;
3. identifique os models existentes;
4. identifique clientes;
5. identifique fornecedores;
6. identifique vendas;
7. identifique usuários;
8. identifique permissões;
9. identifique templates;
10. identifique componentes Tailwind existentes;
11. produza um plano detalhado;
12. NÃO altere o código até concluir a análise.

Depois implemente uma fase por vez.

Após cada fase:

1. executar migrations;
2. executar testes;
3. verificar isolamento multi-tenant;
4. verificar integridade financeira;
5. verificar regressões;
6. somente então avançar para a próxima fase.

Prioridades:

```
1. Integridade financeira
2. Segurança multi-tenant
3. Auditabilidade
4. Consistência transacional
5. Precisão monetária
6. Performance
7. UX
8. Extensibilidade
```

O resultado deve ser um módulo financeiro real, auditável e preparado para integração com o PDV e demais módulos do sistema.


# Implementação do Módulo de Cadastro de Clientes e Onboarding

Você é responsável por implementar o módulo de **cadastro e gerenciamento de clientes da plataforma**.

IMPORTANTE:

Neste módulo, "cliente" significa a pessoa física ou jurídica que **contrata/comprará o uso do sistema**.

Não confundir com:

* cliente de uma loja;
* consumidor final;
* cliente do PDV;
* pessoa que compra um produto da loja.

Este módulo representa o **cliente da plataforma SaaS**.

---

# 1. Contexto da aplicação

A aplicação é um sistema SaaS multi-tenant.

Cada cliente da plataforma poderá possuir um tenant próprio.

O fluxo esperado é:

```
Pessoa/empresa interessada
        ↓
entra em contato
        ↓
equipe da plataforma recebe o contato
        ↓
equipe cadastra o cliente
        ↓
cliente é aprovado/ativado
        ↓
tenant é criado ou associado
        ↓
usuários são criados
        ↓
cliente começa a utilizar o sistema
```

O cadastro do cliente deve existir **independentemente do tenant** durante o processo comercial/onboarding.

---

# 2. Stack obrigatória

O projeto utiliza:

* Python
* Django
* Django Templates
* HTML
* JavaScript
* CSS
* TailwindCSS

Não introduzir:

* React;
* Vue;
* Angular;
* SPA;
* frameworks frontend desnecessários.

Utilizar Django Templates como mecanismo principal de interface.

Utilizar JavaScript apenas quando necessário.

Utilizar TailwindCSS para estilização.

Antes de implementar qualquer coisa, analisar a arquitetura existente.

---

# 3. Multi-tenancy

A aplicação é multi-tenant.

Porém, este módulo possui uma característica especial:

## Cliente da plataforma

O cadastro do cliente é uma entidade de nível administrativo/global.

Ele pode existir:

```
antes do tenant
```

durante:

```
onboarding
```

e posteriormente estar relacionado a:

```
um ou mais recursos de tenant
```

Não aplicar automaticamente o isolamento tradicional de tenant ao model `Cliente` se isso impedir o fluxo de cadastro administrativo.

---

# 4. Separação conceitual

Manter claramente separados:

```
Cliente da Plataforma
```

e:

```
Tenant
```

e:

```
Usuário
```

Exemplo:

```
Cliente
   │
   └── Tenant
          │
          ├── Usuário administrador
          ├── Produtos
          ├── Estoque
          ├── Financeiro
          └── PDV
```

Não assumir que:

```
Cliente = Tenant
```

São conceitos diferentes.

---

# 5. Model Cliente

O model deverá obrigatoriamente possuir:

```
uuid
nome
email
telefone_celular
cpf_cnpj
data_cadastro
observacao
```

Utilizar:

```
UUIDField
```

para `uuid`.

Exemplo conceitual:

```
uuid = UUIDField(
    default=uuid.uuid4,
    editable=False,
    unique=True
)
```

A data de cadastro deverá ser preenchida automaticamente pelo backend:

```
data_cadastro = DateTimeField(
    auto_now_add=True
)
```

Utilizar timezone-aware datetime.

---

# 6. Campos adicionais

Avaliar e adicionar campos úteis.

Sugestão:

```
nome
email
telefone_celular
cpf_cnpj
tipo_pessoa
razao_social
nome_fantasia
data_cadastro
data_atualizacao
observacao
ativo
status
```

Nem todos precisam ser obrigatórios.

---

# 7. Pessoa física/jurídica

Criar:

```
tipo_pessoa
```

com:

```
PF
PJ
```

O campo `cpf_cnpj` deverá ser armazenado de forma consistente.

O sistema deve permitir:

```
CPF
```

ou:

```
CNPJ
```

de acordo com o tipo de pessoa.

Não utilizar somente validação JavaScript.

O backend deve validar.

---

# 8. CPF/CNPJ

Implementar validação de CPF/CNPJ.

A validação deve:

* verificar quantidade de dígitos;
* verificar dígitos verificadores;
* rejeitar documentos obviamente inválidos;
* aceitar entrada com máscara;
* armazenar em formato padronizado.

Recomendação:

armazenar somente os dígitos:

```
12345678901
```

em vez de:

```
123.456.789-01
```

A máscara deve existir somente na apresentação.

O mesmo princípio vale para CNPJ.

Não utilizar biblioteca externa sem necessidade.

Se já existir biblioteca de validação no projeto, reutilizá-la.

---

# 9. Unicidade do documento

O CPF/CNPJ deve possuir unicidade no cadastro de clientes.

Não permitir dois clientes ativos com o mesmo documento.

A regra deve ser garantida no backend e no banco quando possível.

Não depender apenas de:

```
form validation
```

para isso.

---

# 10. E-mail

O e-mail deverá possuir validação adequada.

Considerar:

```
EmailField
```

Não aceitar e-mails obviamente inválidos.

Avaliar se o e-mail deve ser único.

Se for utilizado como login posteriormente, manter essa regra separada da entidade Cliente.

IMPORTANTE:

Não assumir que:

```
Cliente.email
```

será necessariamente:

```
User.email
```

São informações diferentes.

---

# 11. Telefone

Criar campo:

```
telefone_celular
```

O armazenamento deve ser consistente.

Preferencialmente armazenar o telefone em formato normalizado, por exemplo:

```
+5516999999999
```

A interface poderá apresentar máscara.

Não armazenar diferentes formatos para o mesmo número.

---

# 12. Status do cliente

Criar status explícito.

Exemplo:

```
LEAD
EM_ANALISE
PENDENTE
ATIVO
SUSPENSO
CANCELADO
```

Fluxo sugerido:

```
LEAD
  ↓
EM_ANALISE
  ↓
PENDENTE
  ↓
ATIVO
```

Também permitir:

```
ATIVO → SUSPENSO
ATIVO → CANCELADO
```

Não permitir mudanças arbitrárias sem verificar as regras de negócio.

---

# 13. Cliente como Lead

Quando o contato vier através do site, o registro poderá começar como:

```
LEAD
```

A equipe poderá posteriormente transformar esse lead em cliente.

Não criar automaticamente um tenant apenas porque alguém enviou um formulário de contato.

---

# 14. Origem do cliente

Adicionar:

```
origem
```

Exemplos:

```
SITE
TELEFONE
WHATSAPP
INDICACAO
PRESENCIAL
OUTRO
```

Isso será útil para análise comercial futura.

---

# 15. Data de cadastro

Possuir:

```
data_cadastro
```

automaticamente.

Adicionar também:

```
data_atualizacao
```

para permitir auditoria básica.

Não permitir que o usuário altere manualmente `data_cadastro`.

---

# 16. Observação

O campo:

```
observacao
```

deve suportar texto longo.

Utilizar:

```
TextField
```

Pode conter informações administrativas/comerciais.

Não utilizar esse campo para armazenar dados estruturados.

---

# 17. Endereço

Avaliar adicionar endereço.

Se o sistema precisar emitir documentos, contratos ou cobranças, será útil possuir:

```
cep
logradouro
numero
complemento
bairro
cidade
estado
pais
```

Não obrigar todos os campos inicialmente.

Se o projeto já possuir uma estrutura de endereço reutilizável, utilizar a existente.

Não duplicar modelos sem necessidade.

---

# 18. Dados empresariais

Para PJ, avaliar:

```
razao_social
nome_fantasia
inscricao_estadual
```

Não transformar este módulo em um cadastro fiscal completo.

O objetivo é possuir informações suficientes para identificação e onboarding do cliente.

---

# 19. Tenant

O cliente poderá possuir uma relação com um ou mais tenants, dependendo da arquitetura existente.

Exemplo:

```
Cliente
   │
   ├── Tenant Loja A
   └── Tenant Loja B
```

Não assumir que um cliente sempre terá exatamente um tenant.

Porém, se a regra de negócio atual for:

```
1 cliente = 1 tenant
```

implementar essa relação de forma simples e documentada.

Antes de escolher entre:

```
ForeignKey
OneToOneField
ManyToManyField
```

analisar o domínio existente.

Não criar complexidade desnecessária.

---

# 20. Onboarding

Criar conceito de onboarding.

Exemplo:

```
Onboarding
    cliente
    status
    tenant
    data_inicio
    data_conclusao
    usuario_responsavel
    observacao
```

Status:

```
INICIADO
DADOS_PENDENTES
CONFIGURANDO
CONCLUIDO
CANCELADO
```

O objetivo é acompanhar o processo de ativação.

---

# 21. Responsável interno

O cadastro poderá possuir:

```
usuario_responsavel
```

representando o membro da equipe responsável pelo atendimento.

Isso permite saber:

```
quem cadastrou
```

e:

```
quem está cuidando do cliente.
```

Não criar um sistema de usuários separado.

Utilizar o sistema de autenticação existente.

---

# 22. Usuário do cliente

Não criar automaticamente um usuário no momento do cadastro.

O fluxo deve ser:

```
Cliente cadastrado
      ↓
Cliente aprovado
      ↓
Tenant configurado
      ↓
Usuário administrador criado/convidado
```

O usuário de acesso deve possuir seu próprio model/estrutura de autenticação.

Não usar `Cliente` como usuário.

---

# 23. Convite

Preparar arquitetura para convite do cliente.

Futuramente:

```
Cliente aprovado
      ↓
enviar convite
      ↓
cliente cria senha
      ↓
usuário ativado
```

Não armazenar senhas no model Cliente.

Não armazenar tokens de convite em texto permanente sem necessidade.

Utilizar os mecanismos seguros do Django.

---

# 24. Interface administrativa

Criar uma área administrativa para a equipe da plataforma.

Exemplo:

```
/clientes/
```

Com:

* dashboard;
* listagem;
* cadastro;
* detalhes;
* edição;
* ativação;
* suspensão;
* cancelamento;
* onboarding.

---

# 25. Listagem

A tela de clientes deve mostrar:

* nome;
* CPF/CNPJ;
* e-mail;
* telefone;
* status;
* origem;
* responsável;
* data de cadastro;
* tenant associado.

Permitir busca por:

* nome;
* e-mail;
* CPF/CNPJ;
* telefone.

---

# 26. Filtros

Permitir filtros por:

```
status
tipo_pessoa
origem
responsável
período de cadastro
tenant
```

Não carregar todos os clientes para filtrar em JavaScript.

Os filtros devem ser aplicados no backend.

---

# 27. Paginação

A listagem deve possuir paginação.

Não carregar milhares de clientes simultaneamente.

Utilizar paginação nativa do Django ou mecanismo existente no projeto.

---

# 28. Cadastro

Criar formulário contendo:

```
Tipo de pessoa
Nome
Razão social
Nome fantasia
CPF/CNPJ
E-mail
Telefone
Endereço
Origem
Observação
Status
```

O status inicial padrão deve ser:

```
LEAD
```

ou:

```
PENDENTE
```

dependendo da origem do cadastro.

Definir claramente essa regra.

---

# 29. Edição

Permitir editar:

* dados pessoais;
* dados empresariais;
* contato;
* endereço;
* observações;
* responsável.

Não permitir alteração arbitrária de:

```
uuid
data_cadastro
```

---

# 30. Desativação

Evitar excluir fisicamente clientes.

Preferir:

```
status = CANCELADO
```

ou:

```
ativo = False
```

Clientes que possuem histórico comercial, financeiro ou tenant associado não devem ser apagados fisicamente.

---

# 31. Histórico

Criar histórico de alterações importantes.

Exemplo:

```
Cliente criado

Status:
LEAD → EM_ANALISE

Responsável alterado

Cliente ativado

Tenant associado

Cliente suspenso
```

Criar algo como:

```
ClienteHistorico
```

com:

```
uuid
cliente
usuario
acao
status_anterior
status_novo
descricao
data
```

---

# 32. Auditoria

Registrar:

* quem criou;
* quem alterou;
* quando alterou;
* alteração realizada;
* status anterior;
* status novo.

Não depender somente dos logs do Django.

Informações importantes do cliente devem possuir histórico próprio.

---

# 33. Segurança

Somente usuários da equipe autorizada da plataforma poderão acessar o módulo de clientes.

Um usuário comum de um tenant NÃO deve conseguir acessar:

```
/clientes/
```

mesmo conhecendo a URL.

Criar permissões apropriadas.

---

# 34. Permissões

Utilizar o sistema de permissões existente.

Criar permissões como:

```
clients.view_client
clients.add_client
clients.change_client
clients.activate_client
clients.suspend_client
clients.cancel_client
clients.view_history
```

Adaptar ao padrão atual.

Não criar sistema paralelo de autorização.

---

# 35. Separação entre equipe e tenant

É importante distinguir:

```
usuário da plataforma
```

de:

```
usuário de um tenant
```

A equipe administrativa poderá gerenciar clientes.

Usuários de uma loja não devem ter acesso aos clientes da plataforma.

Não resolver isso apenas escondendo links no frontend.

A autorização deve ocorrer no backend.

---

# 36. Página de detalhes

Criar página detalhada:

```
/clientes/<uuid>/
```

Mostrar:

## Dados

* nome;
* CPF/CNPJ;
* e-mail;
* telefone;
* endereço.

## Comercial

* origem;
* responsável;
* status;
* data de cadastro.

## Tenant

* tenant associado;
* status do tenant;
* data de criação.

## Onboarding

* status;
* etapas;
* responsável;
* observações.

## Histórico

* alterações;
* ativação;
* suspensão;
* cancelamento.

---

# 37. Página de onboarding

Criar uma tela específica para acompanhamento.

Exemplo:

```
Dados cadastrais
    ✓

Aprovação
    ✓

Criação do tenant
    ✓

Configuração inicial
    ...

Usuário administrador
    ...

Ativação
    ...
```

Não criar um wizard complexo se o projeto ainda não possuir necessidade.

Uma tela de acompanhamento pode ser suficiente.

---

# 38. Fluxo de ativação

A ativação deve ser uma operação explícita.

Exemplo:

```
Cliente:
    PENDENTE
```

Ao clicar:

```
Ativar cliente
```

o backend deve:

1. verificar permissões;
2. validar dados obrigatórios;
3. criar ou associar tenant;
4. configurar dados mínimos;
5. registrar histórico;
6. atualizar status;
7. iniciar onboarding;
8. não criar usuário automaticamente sem confirmação.

Tudo que puder causar inconsistência deve estar dentro de transação.

---

# 39. Falhas no onboarding

Se ocorrer:

```
erro ao criar tenant
```

não deixar o cliente parcialmente ativado.

Exemplo ruim:

```
Cliente = ATIVO
Tenant = não criado
```

O processo deve ser transacional quando possível.

Se existirem operações externas que não sejam transacionais, implementar estado intermediário e mecanismo de retry.

---

# 40. Site — formulário de contato

O site poderá futuramente possuir:

```
/contato/
```

O visitante preencherá:

```
nome
email
telefone
empresa
mensagem
```

Isso NÃO deve criar automaticamente um cliente ativo.

Criar inicialmente:

```
Lead
```

ou uma entidade de contato.

Avaliar criar:

```
LeadContato
```

se o domínio justificar.

---

# 41. Lead

Se implementado, separar:

```
Lead
```

de:

```
Cliente
```

Exemplo:

```
Lead
   ↓
qualificação
   ↓
Cliente
```

Isso evita poluir o cadastro de clientes com pessoas que apenas solicitaram informações.

---

# 42. Spam e abuso

O formulário público de contato deve possuir proteção contra:

* spam;
* submissões automatizadas;
* flood;
* dados maliciosos.

Utilizar mecanismos já existentes no projeto.

Não confiar somente em JavaScript.

---

# 43. E-mail

Preparar integração futura para:

* confirmação de contato;
* aviso de cadastro;
* convite de acesso;
* ativação;
* suspensão;
* recuperação.

Não implementar envio de e-mail complexo se o projeto ainda não possuir infraestrutura.

---

# 44. LGPD

Como o cadastro contém dados pessoais, tratar os dados de acordo com os princípios aplicáveis da LGPD.

Evitar armazenar informações pessoais desnecessárias.

Não registrar CPF/CNPJ, telefone ou e-mail desnecessariamente em logs.

Não exibir documentos completos em telas onde não sejam necessários.

Considerar mascaramento em listagens.

Exemplo:

```
***.***.***-01
```

quando apropriado.

---

# 45. Logs

Nunca registrar em logs:

* CPF completo;
* CNPJ completo;
* dados sensíveis desnecessários;
* tokens;
* senhas;
* informações de autenticação.

Logs devem conter identificadores técnicos quando possível:

```
cliente_uuid
```

em vez de:

```
CPF completo
```

---

# 46. Banco de dados

Criar índices adequados.

Especialmente:

```
uuid
email
cpf_cnpj
status
data_cadastro
origem
```

Avaliar índices compostos quando fizer sentido.

---

# 47. Normalização

Antes de salvar:

## E-mail

Normalizar caixa quando apropriado.

## Telefone

Normalizar para formato consistente.

## CPF/CNPJ

Remover máscara.

## Nome

Não alterar arbitrariamente a capitalização.

Preservar o nome informado pelo usuário.

---

# 48. Validação

Validar no backend:

* nome;
* e-mail;
* telefone;
* CPF;
* CNPJ;
* tipo de pessoa;
* status;
* origem.

Não confiar somente na validação HTML.

---

# 49. Testes

Criar testes para:

## Cliente

* criação;
* edição;
* UUID;
* data automática;
* validação;
* status.

## CPF/CNPJ

* válido;
* inválido;
* duplicado;
* com máscara;
* sem máscara.

## Multi-tenancy

Testar explicitamente a separação entre:

```
plataforma
tenant
```

E garantir que:

* usuário de tenant não acessa clientes da plataforma;
* usuário sem permissão não acessa clientes;
* cliente A não acessa dados do cliente B através do tenant;
* UUID não permite bypass de autorização.

---

# 50. Testes de ativação

Testar:

```
Cliente PENDENTE
      ↓
ativação
      ↓
Tenant criado
      ↓
Cliente ATIVO
```

Também testar falha:

```
Cliente PENDENTE
      ↓
erro durante criação do tenant
      ↓
operação revertida ou estado intermediário consistente
```

Nunca deixar dados inconsistentes.

---

# 51. Serviços

Separar regras de negócio.

Criar, quando apropriado:

```
ClientService
ClientActivationService
OnboardingService
ClientHistoryService
```

Não colocar toda a lógica em views.

---

# 52. Transações

Utilizar:

```
transaction.atomic()
```

especialmente para:

* ativação;
* criação do tenant;
* associação de tenant;
* alteração de status;
* criação do onboarding.

---

# 53. Futuro módulo de assinatura

Preparar a arquitetura para futuramente adicionar:

```
Plano
Assinatura
Cobrança
Fatura
Pagamento
Trial
```

Não implementar agora.

O cliente poderá futuramente possuir:

```
Cliente
   ↓
Assinatura
   ↓
Plano
   ↓
Tenant
```

Não criar esses modelos agora sem necessidade.

---

# 54. Futuro financeiro

O módulo financeiro da plataforma deverá posteriormente conseguir relacionar:

```
Cliente
   ↓
Assinatura
   ↓
Cobrança
   ↓
Pagamento
```

Não confundir isso com o módulo financeiro interno do tenant.

Existem potencialmente dois contextos financeiros diferentes:

## Financeiro da plataforma

A plataforma cobra o cliente pelo uso do sistema.

## Financeiro do tenant

A loja controla suas próprias entradas, saídas e recebimentos.

Esses dois contextos devem permanecer separados.

---

# 55. Dashboard de clientes

Criar dashboard simples mostrando:

```
Total de clientes
Leads
Pendentes
Ativos
Suspensos
Cancelados
```

E:

```
novos clientes no período
```

Também permitir análise por origem:

```
Site
WhatsApp
Telefone
Indicação
Outros
```

---

# 56. Pesquisa

Permitir busca por:

```
nome
email
CPF/CNPJ
telefone
```

Utilizar busca no banco.

Não carregar todos os registros para JavaScript.

---

# 57. Interface

Utilizar:

* Django Templates;
* TailwindCSS;
* HTML semântico;
* JavaScript vanilla.

Criar componentes reutilizáveis quando o projeto já possuir esse padrão.

Interface responsiva.

---

# 58. URLs

Adaptar aos padrões atuais do projeto.

Estrutura sugerida:

```
/clientes/
/clientes/novo/
/clientes/<uuid>/
/clientes/<uuid>/editar/
/clientes/<uuid>/ativar/
/clientes/<uuid>/suspender/
/clientes/<uuid>/cancelar/
/clientes/<uuid>/historico/
/clientes/<uuid>/onboarding/
```

Operações de alteração devem utilizar POST.

Nunca utilizar GET para:

```
ativar
suspender
cancelar
excluir
```

---

# 59. Critérios de aceite

O módulo será considerado funcional quando:

## Cadastro

A equipe conseguir cadastrar:

```
nome
email
telefone
CPF/CNPJ
observação
```

com:

```
UUID automático
data automática
```

---

## Validação

O sistema deve impedir:

```
CPF inválido
CNPJ inválido
e-mail inválido
documento duplicado
```

---

## Status

Deve ser possível:

```
cadastrar
analisar
ativar
suspender
cancelar
```

com histórico.

---

## Tenant

Ao ativar um cliente:

```
Cliente
    ↓
Tenant
```

deve existir uma relação clara e consistente.

---

## Segurança

Usuários comuns dos tenants não podem acessar:

```
cadastro de clientes da plataforma
```

mesmo conhecendo a URL.

---

## Auditoria

Deve ser possível saber:

```
quem criou
quem alterou
quem ativou
quem suspendeu
quando ocorreu
```

---

# 60. Ordem de implementação

Não implementar tudo simultaneamente.

## Fase 1 — Análise

Antes de escrever código:

1. analisar arquitetura;
2. analisar tenancy;
3. analisar autenticação;
4. analisar usuários;
5. analisar permissões;
6. analisar estrutura administrativa;
7. analisar models existentes;
8. analisar templates;
9. analisar Tailwind;
10. analisar sistema de e-mail;
11. analisar estrutura de contato do site.

Produzir um plano.

Não alterar código antes dessa análise.

---

## Fase 2 — Cliente

Implementar:

* model;
* migrations;
* validações;
* cadastro;
* edição;
* listagem;
* pesquisa;
* filtros;
* detalhes.

---

## Fase 3 — Status e histórico

Implementar:

* status;
* transições;
* histórico;
* auditoria.

---

## Fase 4 — Onboarding

Implementar:

* onboarding;
* responsável;
* tenant;
* ativação;
* associação.

---

## Fase 5 — Contato

Implementar:

* formulário público;
* lead;
* proteção contra spam;
* conversão de lead em cliente.

---

## Fase 6 — Dashboard

Implementar:

* métricas;
* filtros;
* origem;
* evolução de clientes.

---

# 61. Regra final

Antes de escrever código:

1. leia a arquitetura existente;
2. descubra exatamente como o multi-tenancy funciona;
3. descubra como a equipe administrativa é representada;
4. descubra como usuários de tenants são representados;
5. descubra como permissões funcionam;
6. descubra se já existe um sistema de contato/lead;
7. não crie estruturas duplicadas;
8. produza um plano;
9. implemente uma fase por vez.

Nunca confundir:

```
Cliente da plataforma
```

com:

```
Cliente da loja
```

Nunca confundir:

```
Tenant
```

com:

```
Cliente
```

Nunca permitir:

```
usuário de tenant → acesso administrativo global
```

Nunca criar tenant automaticamente a partir de um simples formulário público de contato.

Prioridades:

```
1. Segurança
2. Isolamento entre plataforma e tenants
3. Integridade dos dados
4. Auditoria
5. Simplicidade
6. Extensibilidade
7. UX
```

O módulo deverá servir como base para posteriormente implementar:

```
planos
assinaturas
cobrança
onboarding
usuários
suporte
CRM
financeiro da plataforma
```

sem precisar reestruturar o cadastro de clientes.


# DIRETRIZES ARQUITETURAIS DO PROJETO
# MULTI-TENANT + DJANGO ADMIN + LANDING PAGE

A partir deste momento, trate estas regras como requisitos arquiteturais
obrigatórios para todo o projeto.

Não implemente funcionalidades que violem estas regras.

==================================================
1. VISÃO GERAL DA APLICAÇÃO
==================================================

A aplicação é um sistema SaaS multi-tenant desenvolvido em:

- Python
- Django
- Django Templates
- HTML
- CSS
- JavaScript
- TailwindCSS

A aplicação será utilizada por múltiplos clientes/empresas.

Cada cliente deverá possuir seu próprio ambiente isolado.

Exemplo:

PLATAFORMA
│
├── Cliente A
│     └── Tenant A
│           ├── Usuários
│           ├── Produtos
│           ├── Estoque
│           ├── Financeiro
│           ├── Vendas
│           └── Configurações
│
├── Cliente B
│     └── Tenant B
│           ├── Usuários
│           ├── Produtos
│           ├── Estoque
│           ├── Financeiro
│           ├── Vendas
│           └── Configurações
│
└── Administrador da Plataforma
      └── Django Admin


==================================================
2. REGRA FUNDAMENTAL DE MULTI-TENANCY
==================================================

TODO dado operacional deverá estar associado a um tenant.

Exemplos:

- produtos;
- estoque;
- movimentações de estoque;
- entradas;
- saídas;
- contas a receber;
- movimentações financeiras;
- clientes da loja;
- vendas;
- configurações;
- relatórios;
- documentos;
- usuários pertencentes ao tenant.

Um tenant NUNCA poderá acessar dados pertencentes a outro tenant.

Isso deve ser garantido no BACKEND.

Nunca confiar apenas em:

- URLs;
- UUID;
- IDs;
- parâmetros GET;
- parâmetros POST;
- JavaScript;
- filtros do frontend;
- ocultação de elementos HTML.

O isolamento deve existir na camada de aplicação e, quando apropriado,
também na camada de banco de dados.

==================================================
3. NÃO CONFUNDIR CLIENTE COM TENANT
==================================================

Existem conceitos diferentes:

CLIENTE DA PLATAFORMA:

Pessoa ou empresa que contratou o sistema.

TENANT:

Ambiente isolado utilizado pelo cliente.

USUÁRIO:

Pessoa que possui acesso ao sistema.

Exemplo:

Cliente:
    Empresa ABC

Tenant:
    empresa-abc

Usuário:
    administrador@empresaabc.com.br

Não assumir automaticamente que:

Cliente == Tenant

ou:

Cliente == User


==================================================
4. ADMINISTRADOR DA PLATAFORMA
==================================================

O proprietário/administrador da plataforma deverá possuir acesso total
ao sistema através do Django Admin.

O Django Admin será o painel administrativo central da aplicação.

O administrador deverá conseguir gerenciar, consultar e auditar:

- clientes da plataforma;
- tenants;
- usuários;
- produtos;
- estoque;
- financeiro;
- categorias;
- contas financeiras;
- vendas;
- configurações;
- permissões;
- históricos;
- logs/auditoria;
- demais entidades importantes.

Sempre que um novo model for criado, avaliar obrigatoriamente:

1. Se ele precisa aparecer no Django Admin.
2. Quais campos devem ser exibidos.
3. Quais filtros devem existir.
4. Quais campos devem ser pesquisáveis.
5. Quais relacionamentos devem ser navegáveis.
6. Quais campos não devem ser editáveis.
7. Como evitar alteração acidental de dados financeiros ou históricos.

Não criar models importantes sem registrá-los adequadamente no Django Admin.


==================================================
5. DJANGO ADMIN NÃO É O PAINEL DO TENANT
==================================================

É importante separar:

DJANGO ADMIN
    ↓
Administração global da plataforma

DASHBOARD / INTERFACE DO SISTEMA
    ↓
Operação diária dos tenants

O Django Admin é destinado ao administrador da plataforma.

Os usuários dos tenants utilizarão as interfaces construídas com:

- Django Templates;
- TailwindCSS;
- HTML;
- JavaScript.

Não usar o Django Admin como interface principal das lojas.

==================================================
6. SEGURANÇA DO DJANGO ADMIN
==================================================

Somente usuários autorizados da plataforma poderão acessar:

    /admin/

Usuários normais dos tenants não devem possuir acesso ao Django Admin.

Não confiar apenas na existência de um link.

A autorização deve ser validada pelo Django.

Utilizar corretamente:

- is_staff;
- is_superuser;
- Groups;
- Permissions.

Se o projeto possuir um sistema próprio de usuários, integrá-lo corretamente
ao sistema de autenticação do Django.


==================================================
7. DJANGO ADMIN DEVE SER REALMENTE UTILIZÁVEL
==================================================

Não basta simplesmente fazer:

    admin.site.register(Model)

O Django Admin deve ser configurado de maneira profissional.

Sempre que apropriado, utilizar:

- list_display;
- list_filter;
- search_fields;
- ordering;
- readonly_fields;
- autocomplete_fields;
- list_select_related;
- date_hierarchy;
- fieldsets;
- inlines;
- actions.

Exemplo:

Clientes:

    nome
    email
    telefone
    CPF/CNPJ
    status
    tenant
    data_cadastro

Filtros:

    status
    tipo_pessoa
    origem
    data_cadastro

Pesquisa:

    nome
    email
    CPF/CNPJ


==================================================
8. SEGURANÇA MULTI-TENANT
==================================================

Para cada view operacional, verificar:

    request.user
        ↓
    tenant atual
        ↓
    objeto solicitado
        ↓
    objeto pertence ao tenant?

Somente então permitir acesso.

Nunca fazer simplesmente:

    Model.objects.get(uuid=uuid)

quando o model pertence a um tenant.

Preferir algo equivalente a:

    Model.objects.get(
        uuid=uuid,
        tenant=current_tenant
    )

ou utilizar uma camada de serviço/selector que aplique
automaticamente o tenant.

==================================================
9. NÃO CONFIAR NO TENANT ENVIADO PELO FRONTEND
==================================================

Nunca aceitar algo como:

    tenant_id = request.POST["tenant"]

como fonte de verdade.

O tenant deve ser determinado pelo contexto autenticado do usuário.

O frontend não decide qual tenant está sendo acessado.

O backend decide.


==================================================
10. QUERYSETS
==================================================

Sempre que um model for tenant-aware, seus QuerySets devem respeitar
o tenant atual.

Evitar código como:

    Product.objects.all()

em uma view de tenant.

Preferir:

    Product.objects.filter(
        tenant=current_tenant
    )

ou utilizar uma abstração centralizada.

Se o projeto possuir um TenantManager, TenantQuerySet ou mecanismo
equivalente, reutilizá-lo.


==================================================
11. SERVICES
==================================================

Regras de negócio importantes não devem ficar espalhadas pelas views.

Utilizar services/selectors quando apropriado.

Exemplo:

    ProductService
    InventoryService
    FinancialService
    TenantService
    ClientService

Esses serviços devem respeitar o tenant atual.

Não criar serviços que permitam alterar dados de outro tenant
sem uma verificação explícita de autorização.


==================================================
12. MODELS TENANT-AWARE
==================================================

Sempre que um model pertencer a um tenant, avaliar uma estrutura
semelhante a:

    tenant
    uuid
    ...

O tenant deve ser obrigatório quando o domínio exigir.

Evitar:

    tenant = null=True

sem justificativa arquitetural.

Dados que não pertencem a um tenant específico podem ser globais.

Exemplos:

    Tenant
    Cliente da plataforma
    Plano
    Configuração global

Dados operacionais normalmente são tenant-aware.

Exemplos:

    Produto
    Estoque
    Venda
    Financeiro
    Cliente da loja


==================================================
13. DJANGO ADMIN E MULTI-TENANCY
==================================================

O administrador da plataforma deve conseguir visualizar dados
de TODOS os tenants.

Por isso, o Django Admin deve funcionar em uma perspectiva global.

Exemplo:

    Admin
      ↓
    Tenant A
      ├── Produtos
      ├── Financeiro
      └── Vendas

    Tenant B
      ├── Produtos
      ├── Financeiro
      └── Vendas

O administrador deve conseguir:

- pesquisar;
- filtrar por tenant;
- visualizar;
- editar;
- auditar.

Adicionar filtros por tenant nos models tenant-aware.

Exemplo:

    list_filter = (
        "tenant",
        "status",
    )


==================================================
14. IDENTIFICAÇÃO DOS TENANTS
==================================================

Todo tenant deverá possuir um identificador único.

Utilizar UUID para identificadores técnicos quando apropriado.

Também considerar:

    nome
    slug
    status
    data_criacao
    data_atualizacao

O slug poderá ser utilizado para URLs quando fizer sentido.

Não utilizar nome como identificador técnico.


==================================================
15. STATUS DO TENANT
==================================================

Preparar o tenant para possuir estados como:

    PENDENTE
    ATIVO
    SUSPENSO
    CANCELADO

A aplicação deverá respeitar o status.

Por exemplo:

Tenant SUSPENSO:

    não deve permitir operação normal

mas:

    administrador da plataforma
    continua podendo acessar os dados pelo Django Admin.


==================================================
16. AUDITORIA
==================================================

Operações administrativas importantes devem ser auditáveis.

Registrar quando apropriado:

- usuário;
- tenant;
- ação;
- entidade;
- data/hora;
- alteração.

Especialmente:

- criação;
- alteração;
- exclusão;
- ativação;
- suspensão;
- cancelamento;
- operações financeiras.

Não apagar dados financeiros importantes sem histórico.


==================================================
17. EXCLUSÃO
==================================================

Não utilizar exclusão física indiscriminadamente.

Para entidades importantes, avaliar:

    ativo
    status
    deleted_at

ou mecanismo equivalente.

Especialmente:

- clientes;
- tenants;
- produtos com movimentações;
- registros financeiros;
- vendas.

Dados históricos importantes devem permanecer disponíveis.


==================================================
18. UUID
==================================================

Entidades importantes deverão utilizar UUID.

Exemplo:

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False
    )

Não expor IDs incrementais desnecessariamente nas URLs públicas.

O UUID é identificador técnico.

Não utilizar UUID como substituto de autorização.

Mesmo conhecendo um UUID, o usuário não pode acessar
um objeto de outro tenant.


==================================================
19. BANCO DE DADOS
==================================================

Criar índices apropriados.

Para models tenant-aware, avaliar índices compostos:

    tenant + uuid
    tenant + status
    tenant + created_at
    tenant + nome

Não criar índices indiscriminadamente.

Analisar as consultas reais da aplicação.


==================================================
20. PERFORMANCE
==================================================

A aplicação poderá possuir muitos tenants e muitos registros.

Portanto:

- evitar N+1;
- utilizar select_related;
- utilizar prefetch_related;
- utilizar agregações no banco;
- utilizar paginação;
- evitar carregar tabelas inteiras;
- filtrar por tenant;
- criar índices adequados.

Relatórios financeiros devem ser calculados no banco sempre que possível.


==================================================
21. LANDING PAGE
==================================================

Criar uma landing page pública para apresentação da aplicação.

Idioma:

    Português do Brasil (pt-BR)

Não utilizar textos em inglês.

A landing page deve ser:

- simples;
- moderna;
- profissional;
- limpa;
- responsiva;
- rápida;
- objetiva.

Não criar uma landing page excessivamente complexa.

O objetivo é apresentar o produto e incentivar o visitante
a entrar em contato.


==================================================
22. ESTRUTURA DA LANDING PAGE
==================================================

Criar uma página inicial pública:

    /

Estrutura sugerida:

    Header
        Logo/Nome da aplicação
        Recursos
        Benefícios
        Contato
        Botão "Fale conosco"

    Hero
        Título forte
        Subtítulo
        CTA
        imagem/ilustração simples

    Recursos
        Gestão de produtos
        Controle de estoque
        Financeiro
        Vendas / PDV
        Relatórios

    Benefícios
        Organização
        Controle
        Segurança
        Multi-tenant

    Como funciona
        Cadastro
        Configuração
        Uso

    CTA final
        "Pronto para simplificar a gestão da sua empresa?"

    Footer
        Nome da aplicação
        Links
        Contato
        Direitos autorais


==================================================
23. TEXTO DA LANDING PAGE
==================================================

Criar textos em português brasileiro.

Evitar linguagem excessivamente técnica.

Exemplo de Hero:

    "Gestão simples para o seu negócio."

Subtítulo:

    "Controle produtos, estoque, vendas e financeiro em um único lugar."

CTA:

    "Quero conhecer"

ou:

    "Fale conosco"


==================================================
24. RECURSOS DA APLICAÇÃO
==================================================

Apresentar os principais módulos.

### Produtos

"Cadastre e organize seus produtos de forma rápida e prática."

### Estoque

"Tenha controle das entradas, saídas e movimentações do seu estoque."

### Financeiro

"Controle entradas, saídas, recebimentos e acompanhe a saúde financeira do negócio."

### Vendas

"Centralize suas vendas e tenha uma visão completa das operações."

### Relatórios

"Transforme os dados da sua operação em informações úteis para tomar decisões."


==================================================
25. MULTI-TENANT NA LANDING PAGE
==================================================

Apresentar o conceito de forma simples.

Não usar termos técnicos como:

    isolamento de banco
    tenant-aware queryset
    row-level security

O usuário final não precisa conhecer a implementação.

Usar algo como:

    "Cada empresa possui seu próprio ambiente,
     com seus dados organizados e protegidos."

==================================================
26. DESIGN
==================================================

Utilizar TailwindCSS.

Visual:

- moderno;
- minimalista;
- profissional;
- bastante espaço em branco;
- tipografia clara;
- cards discretos;
- bordas suaves;
- sombras leves;
- boa hierarquia visual.

Evitar:

- excesso de gradientes;
- excesso de animações;
- carrosséis desnecessários;
- efeitos exagerados;
- dezenas de cores;
- componentes visualmente poluídos.


==================================================
27. RESPONSIVIDADE
==================================================

A landing page deve funcionar bem em:

- desktop;
- notebook;
- tablet;
- celular.

Testar principalmente:

    320px
    375px
    768px
    1024px
    1440px


==================================================
28. ACESSIBILIDADE
==================================================

Utilizar:

- HTML semântico;
- labels;
- contraste adequado;
- navegação por teclado;
- alt em imagens;
- botões semanticamente corretos;
- headings hierárquicos.

Não utilizar divs para tudo.


==================================================
29. SEO BÁSICO
==================================================

Adicionar:

    <title>

    <meta name="description">

    viewport

Open Graph básico quando apropriado.

Exemplo:

    title:
    "Nome da Aplicação — Gestão simples para o seu negócio"

Description:

    "Sistema completo para gestão de produtos,
     estoque, vendas e financeiro."


==================================================
30. PERFORMANCE DA LANDING PAGE
==================================================

Não adicionar bibliotecas JavaScript pesadas.

Evitar dependências desnecessárias.

Priorizar:

    HTML
    CSS/Tailwind
    JavaScript mínimo

Imagens devem ser otimizadas.

A página deve carregar rapidamente.


==================================================
31. ESTRUTURA DE URLs
==================================================

Utilizar URLs claras.

Exemplo:

    /
        landing page

    /contato/
        formulário de contato

    /login/
        autenticação

    /app/
        aplicação do tenant

    /admin/
        Django Admin

Não misturar a área administrativa global com a aplicação do tenant.


==================================================
32. CONTATO
==================================================

A landing page deve possuir CTA direcionando para:

    /contato/

O formulário deve permitir:

    Nome
    Empresa
    E-mail
    Telefone
    Mensagem

O formulário deverá gerar um lead/solicitação de contato.

Não criar automaticamente um tenant.

Não ativar automaticamente um cliente.

O administrador deverá analisar o contato primeiro.


==================================================
33. FLUXO COMPLETO
==================================================

O fluxo comercial esperado é:

VISITANTE
    ↓
LANDING PAGE
    ↓
CONTATO
    ↓
LEAD
    ↓
ADMINISTRADOR
    ↓
CADASTRO DO CLIENTE
    ↓
APROVAÇÃO
    ↓
CRIAÇÃO DO TENANT
    ↓
CONFIGURAÇÃO
    ↓
CRIAÇÃO/CONVITE DO USUÁRIO
    ↓
ATIVAÇÃO
    ↓
CLIENTE UTILIZA A APLICAÇÃO


==================================================
34. INTERFACE DO TENANT
==================================================

A aplicação utilizada pelo cliente deverá possuir:

    Dashboard
    Produtos
    Estoque
    Financeiro
    Vendas
    Relatórios
    Configurações

Todos os módulos deverão respeitar o tenant atual.

O usuário nunca deverá precisar informar manualmente:

    tenant_id

para operações normais.


==================================================
35. ADMINISTRADOR
==================================================

O administrador da plataforma deverá conseguir:

### Clientes

- cadastrar;
- editar;
- ativar;
- suspender;
- cancelar;
- visualizar histórico.

### Tenants

- criar;
- visualizar;
- editar;
- ativar;
- suspender;
- cancelar.

### Usuários

- criar;
- editar;
- ativar;
- desativar;
- alterar permissões.

### Dados

- visualizar dados dos tenants;
- pesquisar;
- filtrar por tenant;
- auditar.

### Sistema

- categorias;
- configurações;
- permissões;
- parâmetros globais.


==================================================
36. DJANGO ADMIN COMO FERRAMENTA DE OPERAÇÃO
==================================================

O administrador NÃO deve depender de scripts SQL para realizar
operações administrativas normais.

Sempre que uma operação fizer parte da administração normal do sistema,
ela deverá estar disponível através do Django Admin ou de uma interface
administrativa própria quando o Django Admin não for adequado.

Exemplo:

Criar tenant:

    Django Admin

Visualizar clientes:

    Django Admin

Suspender tenant:

    Django Admin

Consultar financeiro:

    Django Admin

Gerenciar usuários:

    Django Admin


==================================================
37. AÇÕES DO ADMIN
==================================================

Quando apropriado, criar Django Admin Actions.

Exemplos:

    Ativar selecionados
    Suspender selecionados
    Marcar como pendente
    Exportar selecionados

Operações destrutivas devem exigir confirmação.


==================================================
38. INLINE ADMIN
==================================================

Utilizar inlines quando fizer sentido.

Exemplo:

Tenant:

    Tenant
       ├── Usuários
       ├── Configurações
       └── Dados relacionados

Cliente:

    Cliente
       ├── Histórico
       └── Onboarding

Evitar inlines gigantes que prejudiquem performance.


==================================================
39. DOCUMENTAÇÃO
==================================================

Criar documentação arquitetural explicando:

- o que é tenant;
- o que é cliente;
- o que é usuário;
- como o isolamento funciona;
- como o administrador acessa os dados;
- como criar tenant;
- como testar isolamento;
- como funciona o onboarding.

Essa documentação deverá ser útil para futuros desenvolvedores.


==================================================
40. TESTES OBRIGATÓRIOS
==================================================

Criar testes para provar:

### Tenant isolation

Tenant A:

    Produto A

Tenant B:

    Produto B

Usuário A:

    pode acessar Produto A

Usuário A:

    NÃO pode acessar Produto B


### Financeiro

Tenant A:

    R$ 1.000

Tenant B:

    R$ 5.000

Análise de Tenant A:

    R$ 1.000

Nunca:

    R$ 6.000


### URLs

Usuário A tenta acessar:

    /produto/<uuid-do-produto-do-tenant-B>/

Resultado:

    404 ou 403

Nunca:

    dados do Tenant B


### Admin

Administrador:

    consegue visualizar Tenant A
    consegue visualizar Tenant B

Usuário comum:

    não consegue acessar /admin/


==================================================
41. REGRAS DE IMPLEMENTAÇÃO
==================================================

Antes de alterar código:

1. Leia o projeto.
2. Identifique a arquitetura atual.
3. Identifique como o tenancy está implementado.
4. Identifique o model User.
5. Identifique como os tenants são representados.
6. Identifique como permissões funcionam.
7. Identifique o layout atual.
8. Identifique o sistema Tailwind.
9. Identifique o sistema de URLs.
10. Identifique os models existentes.
11. Identifique o Django Admin existente.

NÃO crie uma nova arquitetura de tenancy se já existir uma.

NÃO substitua o sistema de autenticação existente sem necessidade.

NÃO introduza frameworks frontend.

NÃO duplicar models ou serviços existentes.


==================================================
42. ANTES DE CODIFICAR
==================================================

Primeiro apresente:

1. arquitetura atual encontrada;
2. implementação atual de tenancy;
3. implementação atual de autenticação;
4. implementação atual do Django Admin;
5. models existentes relevantes;
6. possíveis conflitos;
7. plano de implementação;
8. estrutura proposta para a landing page.

Somente depois implemente.


==================================================
43. CRITÉRIO DE ACEITE FINAL
==================================================

Ao finalizar, o sistema deverá possuir:

[ ] Multi-tenancy funcional
[ ] Isolamento entre tenants
[ ] Administrador global
[ ] Django Admin configurado
[ ] Models importantes registrados no Admin
[ ] Filtros por tenant
[ ] Permissões adequadas
[ ] Auditoria
[ ] Cliente da plataforma separado do tenant
[ ] Onboarding preparado
[ ] Landing page pública
[ ] Landing page em pt-BR
[ ] Landing page responsiva
[ ] Página de contato
[ ] SEO básico
[ ] Testes de isolamento
[ ] Testes de permissões
[ ] Documentação arquitetural


==================================================
44. REGRA MAIS IMPORTANTE
==================================================

NUNCA implemente uma funcionalidade assumindo que existe apenas uma empresa.

O sistema deverá ser projetado desde o início para:

    1 plataforma
        ↓
    N clientes
        ↓
    N tenants
        ↓
    N usuários
        ↓
    N registros operacionais

Todo código novo deverá ser avaliado sob esta perspectiva.

Se uma decisão arquitetural puder comprometer o isolamento entre tenants,
PARE e apresente o problema antes de implementar.

Prioridades:

1. Segurança
2. Isolamento multi-tenant
3. Integridade dos dados
4. Administração via Django Admin
5. Auditabilidade
6. Manutenibilidade
7. Performance
8. Experiência do usuário
9. Design