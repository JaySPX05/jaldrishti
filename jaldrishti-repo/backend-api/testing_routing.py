from routing import build_synthetic_graph, dijkstra

graph = build_synthetic_graph()

route, distance = dijkstra(
    graph,
    "A",
    "F",
)

print("Route:", route)
print("Distance:", distance)
