if __name__ == '__main__':
    from src.identity import configure_process_identity
    configure_process_identity()
    from config import config
    from ok import OK

    config = config
    ok = OK(config)
    ok.start()
