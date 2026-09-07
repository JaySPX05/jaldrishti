import heapq


def build_synthetic_graph():
    roads = [
        ("A", "B", 200),
        ("A", "C", 150),
        ("B", "C", 100),
        ("B", "D", 250),
        ("C", "D", 400),
        ("C", "E", 500),
        ("D", "E", 100),
        ("D", "F", 300),
        ("E", "F", 150),
    ]

    graph = {}

    for source, destination, distance in roads:
        graph.setdefault(source, []).append(
            (destination, distance)
        )

        graph.setdefault(destination, []).append(
            (source, distance)
        )

    return graph


def dijkstra(graph, start, goal, blocked_edges=None):
    if start not in graph or goal not in graph:
        return None, float("inf")

    if start == goal:
        return [start], 0

    if blocked_edges is None:
        blocked_edges = set()

    distances = {
        node: float("inf")
        for node in graph
    }

    previous = {
        node: None
        for node in graph
    }

    distances[start] = 0
    priority_queue = [(0, start)]

    while priority_queue:
        current_distance, current_node = heapq.heappop(
            priority_queue
        )

        if current_distance > distances[current_node]:
            continue

        if current_node == goal:
            break

        for neighbour, edge_weight in graph[current_node]:
            if (current_node, neighbour) in blocked_edges:
                continue

            new_distance = current_distance + edge_weight

            if new_distance < distances[neighbour]:
                distances[neighbour] = new_distance
                previous[neighbour] = current_node

                heapq.heappush(
                    priority_queue,
                    (new_distance, neighbour)
                )

    if distances[goal] == float("inf"):
        return None, float("inf")

    route = []
    current = goal

    while current is not None:
        route.append(current)
        current = previous[current]

    route.reverse()

    return route, distances[goal]


def get_route_edges(route):
    if route is None or len(route) < 2:
        return []

    return [
        (route[index], route[index + 1])
        for index in range(len(route) - 1)
    ]
