ZEN = "".join(chr(0xFF01 + i) for i in range(94))
HAN = "".join(chr(0x21 + i) for i in range(94))
HAN2ZEN = str.maketrans(HAN, ZEN)


# 半角から全角
def han2zen(query: str) -> str:
    # 半角から全角
    return query.translate(HAN2ZEN)
