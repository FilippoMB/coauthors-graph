📚 Create and visualize with [Gravis](https://robert-haas.github.io/gravis-docs/) your co-authors graph based on your articles on the [DBLP](https://dblp.org/) database.

Each node in the graph is a co-author. The size of the node is proportional to its degree, so the larger the node the more a co-author published with other co-authors in the graph. The size of the edges are proportional to the number of different papers two authors published. The nodes are colored based on their community. Yourself is a black node in the middle with a fixed size.

The graph will be saved in a file called `coauthors.html`. It can be visualized in your browser or any other html renderer. 
<div align="center">
 Mine is this [one](https://htmlpreview.github.io/?https://github.com/FilippoMB/coauthors-graph/blob/main/coauthors.html).
</div>
<br>

# 🚀 Create your own graph

## 🎓 Get your DBLP ID

- Go to [DBLP](https://dblp.org/) and write your name in the search bar.
- Under "Exact macthces" your name should pop up.
- Click on it, and you should be redirected to a page like this: `https://dblp.org/pid/139/5968.html`.
- The digits at the end representyour DBLP ID, e.g, mine is `139/5968`.

## ⚙️ Modify the configuration file

Modify the following entries in `config.json`:

- `"author_name"` put your own name with initials, e.g., `"F. M. Bianchi"`.
- `"author_id"` put the DBLP ID that you extracted before, e.g., `"139/5968"`.

There are few other optional parameters to set.

- `"base_node_size"`, `"degree_multiplier"`, `"base_edge_size"`, and `"edge_size_multiplier"`can be adjusted until your own graph renders nicely by following a trial and error approach.
- Some of the names of your co-authors can be duplicated or appear with a a numerical code in front of it. Specify the wrong and the corrected version of your co-authors names in `"to_fix"`.
- The communities are colored by default using modularity. You can also use the Louvain community detection algorithm by setting `"community_algo": "louvain"`.

## 💻 Install dependencies and run the script

````bash
pip install matplotlib networkx gravis selenium
````

````bash
python main.py
````
