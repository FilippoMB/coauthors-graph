import requests
import xml.etree.ElementTree as ET
import networkx as nx
import matplotlib.pyplot as plt
import matplotlib
import gravis as gv
import os
import json
import numpy as np

### Util functions ###############
def fetch_dblp_data(author_id):
    url = f"https://dblp.org/pid/{author_id}.xml"
    response = requests.get(url)
    if response.status_code == 200:
        return ET.fromstring(response.content)
    return None

def parse_dblp_xml(data):
    publications = []
    for pub in data.findall('.//article') + data.findall('.//inproceedings'):
        authors = [author.text for author in pub.findall('.//author')]
        publications.append(authors)
    return publications

def load_config(filename):
    with open(filename, 'r') as file:
        config = json.load(file)
    return config
##################################

# Load the configuration
config = load_config('config.json')

# Fetch data
data = fetch_dblp_data(config['author_id'])

# Parse XML
publications = parse_dblp_xml(data)

# Fix errors in the names
for old, new in config['to_fix']:
    for publication in publications:
        for i, author in enumerate(publication):
            if author == old:
                publication[i] = new

# Replace full names with initials
for publication in publications:
    for i, author in enumerate(publication):
        names = author.split()
        publication[i] = ' '.join([name[0] + '.' for name in names[:-1]]) + ' ' + names[-1]

# Bulid the graph
G = nx.Graph()
for publication in publications:
    for author in publication:
        if author not in G.nodes:
            G.add_node(author)
    for author1 in publication:
        for author2 in publication:
            if author1 != author2:
                if G.has_edge(author1, author2):
                    if author1 == config['author_name'] or author2 == config['author_name']:
                        G[author1][author2]['weight'] += 1
                else:
                    G.add_edge(author1, author2, weight=1)

# Find communities
if config['community_algo'] == 'louvain':
    communities = nx.community.louvain_communities(G, seed=123, resolution=1.5)
elif config['community_algo'] == 'modularity':
    communities = nx.community.greedy_modularity_communities(G, resolution=1.5)
else:
    raise ValueError('Invalid community algorithm')

# Colors
black = '#000000'
gray = '#808080'
cmap = plt.get_cmap("tab10")
cmap_hex = [matplotlib.colors.rgb2hex(cmap(i)) for i in range(len(cmap.colors))]

# Edges properties
for u, v in G.edges:
    G[u][v]['color'] = gray + '80'
    G[u][v]['size'] =  G[u][v]['weight']*config['edge_size_multiplier'] + config['base_edge_size']

    # If two nodes are in the same community, color the edge with the community color
    for i, community in enumerate(communities):
        if u != config['author_name'] and v != config['author_name']:
            if u in community and v in community:
                G[u][v]['color'] = cmap_hex[i%len(cmap_hex)] + '80'
                break

# Nodes properties
for node_id in G.nodes:
    node = G.nodes[node_id]

    # If the node is the main author, skip (we'll set size later).
    if node_id == config['author_name']:
        continue

    # Otherwise, determine how many publications this node shares with the main author
    coauthor_count = G[node_id][config['author_name']]['weight'] #if G.has_edge(node_id, config['author_name']) else 0

    # Example: offset by 1 to avoid log(0), then multiply
    node_size = config['base_node_size'] + config['node_size_multiplier'] * np.log1p(coauthor_count)  # log1p(x) is log(x+1)

    node['size'] = node_size

    # Color a node based on the community it belongs to
    for i, community in enumerate(communities):
        if node_id in community:
            node['color'] = cmap_hex[i%len(cmap_hex)]
            break
    node['border_size'] = 1
    node['border_color'] = 'white'

# Set the author node properties
G.nodes[config['author_name']]['size'] = 40
G.nodes[config['author_name']]['color'] = black

# Plot the graph
fig = gv.d3(G, graph_height=800,
      layout_algorithm_active=True,
      many_body_force_strength=-700.0,
      edge_curvature=0.1,
      links_force_distance=100.0,
      links_force_strength=0.6)
fig.display()

# Save the html file
file_name = 'coauthors.html'
try:
    os.remove(file_name)
except FileNotFoundError:
    pass
fig.export_html('coauthors.html')