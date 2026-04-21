def read_message():
    with open("data/message.txt", encoding="utf-8") as handle:
        return handle.read().strip()
