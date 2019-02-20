def main():
    try:
        foo
    except NameError:
        foo = False

    if foo:
        assert False
    else:
        try:
            main.foo
        except AttributeError:
            msg = "couldn't do that"
            raise AttributeError(msg)


try:
    main()
except AttributeError as e:
    assert "couldn't" in str(e)
else:
    assert False, 'Did not see ImportError.'
