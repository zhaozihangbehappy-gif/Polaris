def classify(x: int) -> str:
    match x:
        case 0:
            return "zero"
        case 1 | 2 | 3:
            return "small"
        case _:
            return "other"


if __name__ == "__main__":
    print(classify(1))
