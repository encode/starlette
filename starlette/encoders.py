def utf8encoder(val):
    if isinstance(val, bytes):
        return val.decode('utf-8')
