import configparser


def main():
    config = configparser.ConfigParser()
    config.read("settings.ini")
    port = config.getint("server", "port")
    print(f"server port: {port}")


if __name__ == "__main__":
    main()
