def distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def is_near(a, b, radius=5):
    return distance(a, b) <= radius