def make_chain(depth):
    value = "leaf"
    for _ in range(depth):
        value = [value]
    return value


def leaf_depth(node):
    if not isinstance(node, list):
        return 0
    return 1 + leaf_depth(node[0])
