"""Chave de acesso da NFC-e (43 dígitos + DV mod-11).

Composição oficial (leiaute 4.00, Portal Nacional da NF-e):
cUF(2) | AAMM(4) | CNPJ(14) | mod(2) | serie(3) | nNF(9) | tpEmis(1)
| cNF(8) → 43 posições + cDV(1).

Dígito verificador: pesos de 2 a 9 aplicados da direita para a esquerda;
resto da divisão por 11; DV = 11 − resto, assumindo 0 quando o resultado
for 10 ou 11.
"""

from dataclasses import dataclass

MODELO_NFCE = "65"


class ChaveInvalida(ValueError):
    """Chave de acesso malformada ou com DV incorreto."""


def calcular_dv(digitos_43: str) -> int:
    """Calcula o DV mod-11 de uma base de exatamente 43 dígitos."""
    if len(digitos_43) != 43 or not digitos_43.isdigit():
        raise ChaveInvalida("Base da chave deve ter 43 dígitos numéricos.")
    soma = 0
    peso = 2
    for caractere in reversed(digitos_43):
        soma += int(caractere) * peso
        peso = 2 if peso == 9 else peso + 1
    resto = soma % 11
    dv = 11 - resto
    return 0 if dv >= 10 else dv


@dataclass(frozen=True)
class ChaveAcesso:
    cuf: str
    aamm: str
    cnpj: str
    modelo: str = MODELO_NFCE
    serie: int = 1
    numero: int = 1
    tp_emis: str = "1"
    cnf: str = "00000001"

    def __post_init__(self):
        if not self.cuf.isdigit() or len(self.cuf) != 2:
            raise ChaveInvalida("cUF deve ter 2 dígitos.")
        if not self.aamm.isdigit() or len(self.aamm) != 4:
            raise ChaveInvalida("AAMM deve ter 4 dígitos (ano/mês).")
        if not self.cnpj.isdigit() or len(self.cnpj) != 14:
            raise ChaveInvalida("CNPJ deve ter 14 dígitos.")
        if not 1 <= self.serie <= 999:
            raise ChaveInvalida("Série deve estar entre 1 e 999.")
        if not 1 <= self.numero <= 999999999:
            raise ChaveInvalida("Número deve estar entre 1 e 999999999.")

    @property
    def base(self) -> str:
        return (
            f"{self.cuf}{self.aamm}{self.cnpj}"
            f"{self.modelo}{self.serie:03d}{self.numero:09d}"
            f"{self.tp_emis}{int(self.cnf):08d}"
        )

    @property
    def dv(self) -> int:
        return calcular_dv(self.base)

    @property
    def completa(self) -> str:
        """44 dígitos incluindo o DV."""
        return f"{self.base}{self.dv}"

    def __str__(self):
        return self.completa

    @classmethod
    def da_string(cls, chave: str) -> "ChaveAcesso":
        """Reconstrói a chave a partir dos 44 dígitos armazenados."""
        if not validar(chave):
            raise ChaveInvalida("Chave de acesso inválida.")
        campos = decompor(chave)
        return cls(
            cuf=campos["cuf"],
            aamm=campos["aamm"],
            cnpj=campos["cnpj"],
            modelo=campos["modelo"],
            serie=campos["serie"],
            numero=campos["numero"],
            tp_emis=campos["tp_emis"],
            cnf=campos["cnf"],
        )


def validar(chave: str) -> bool:
    """Valida formato e DV de uma chave completa de 44 dígitos."""
    if not isinstance(chave, str) or len(chave) != 44 or not chave.isdigit():
        return False
    try:
        return calcular_dv(chave[:43]) == int(chave[43])
    except ChaveInvalida:
        return False


def decompor(chave: str) -> dict:
    """Decompõe a chave em seus campos oficiais."""
    if not validar(chave):
        raise ChaveInvalida("Chave inválida.")
    return {
        "cuf": chave[0:2],
        "aamm": chave[2:6],
        "cnpj": chave[6:20],
        "modelo": chave[20:22],
        "serie": int(chave[22:25]),
        "numero": int(chave[25:34]),
        "tp_emis": chave[34],
        "cnf": chave[35:43],
        "dv": int(chave[43]),
    }
