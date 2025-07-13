from pathlib import Path

def level(line):
    """
    Determine the level of indentation based on the number of leading |.
    """
    res = 0
    for c in line:
        if c == '|':
            res += 1
        elif c == ' ':
            continue
        else:
            break
    
    return res


