"""Validação de documentos brasileiros (CPF/CNPJ) sem dependências externas."""

import re

CPF_LENGTH = 11
CNPJ_LENGTH = 14

_ONLY_DIGITS = re.compile(r"\D")


def only_digits(value):
    """Remove máscara, mantendo apenas dígitos."""
    return _ONLY_DIGITS.sub("", value or "")


def _calculate_check_digits(digits, weights_first, weights_second):
    total = sum(int(d) * w for d, w in zip(digits, weights_first, strict=True))
    remainder = (total * 10) % 11
    first = 0 if remainder == 10 else remainder
    digits = digits + str(first)
    total = sum(int(d) * w for d, w in zip(digits, weights_second, strict=True))
    remainder = total % 11
    second = 0 if remainder < 2 else 11 - remainder
    return f"{first}{second}"


def is_valid_cpf(value):
    """Valida CPF (com ou sem máscara)."""
    cpf = only_digits(value)
    if len(cpf) != CPF_LENGTH or cpf == cpf[0] * CPF_LENGTH:
        return False
    expected = _calculate_check_digits(
        cpf[:9],
        range(10, 1, -1),
        range(11, 1, -1),
    )
    return cpf[9:] == expected


def is_valid_cnpj(value):
    """Valida CNPJ (com ou sem máscara)."""
    cnpj = only_digits(value)
    if len(cnpj) != CNPJ_LENGTH or cnpj == cnpj[0] * CNPJ_LENGTH:
        return False
    expected = _calculate_check_digits(
        cnpj[:12],
        list(range(5, 1, -1)) + list(range(9, 1, -1)),
        list(range(6, 1, -1)) + list(range(9, 1, -1)),
    )
    return cnpj[12:] == expected


def validate_cpf_cnpj(value):
    """Valida CPF ou CNPJ conforme o tamanho do documento informado.

    Retorna os dígitos normalizados. Levanta ValueError quando inválido.
    """
    digits = only_digits(value)
    if len(digits) == CPF_LENGTH:
        if not is_valid_cpf(digits):
            raise ValueError("CPF inválido.")
        return digits
    if len(digits) == CNPJ_LENGTH:
        if not is_valid_cnpj(digits):
            raise ValueError("CNPJ inválido.")
        return digits
    raise ValueError("Documento deve conter 11 dígitos (CPF) ou 14 dígitos (CNPJ).")
