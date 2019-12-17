def remove_at_hex(s):
    pieces = s.split()
    while True:
        try:
            i = pieces.index('at')
        except ValueError:
            return ' '.join(pieces)
        else:
            pieces[i:i+2] = []
