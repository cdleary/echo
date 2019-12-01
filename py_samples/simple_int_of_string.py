try:
    int('shoobadooba')
except ValueError as e:
    assert "invalid literal for int() with base 10: 'shoobadooba'" == str(e), e
except:
    assert False, 'Did not flag error for invalid int conversion.'
