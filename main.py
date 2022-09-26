# Inspired by: https://www.debuggingbook.org/beta/html/DeltaDebugger.html#Reducing-Failure-Inducing-Inputs
from ast import iter_child_nodes, parse, unparse, operator, Name, NodeTransformer, NodeVisitor, AST
from collections import deque
import copy
from typing import Any

class NodeCollector(NodeVisitor):
    def __init__(self) -> None:
        super().__init__()
        self.nodes: list[AST] = []

    def generic_visit(self, node: AST) -> None:
        self.nodes.append(node)
        return super().generic_visit(node)
        
    def collect(self, tree: AST) -> list[AST]:
        """ Return a nodes in a given tree. """
        self.nodes: list[AST] = []
        self.visit(tree)
        return self.nodes

class NodeMarker(NodeVisitor):
    def visit(self, node: AST) -> AST:
        node.marked = True
        return super().generic_visit(node)

class NodeReducer(NodeTransformer):
    def visit(self, node: AST) -> Any:
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)
    
    def visit_Module(self, node: AST) -> Any:
        # Can't remove modules
        return super().generic_visit(node)

    def generic_visit(self, node: AST) -> Any:
        hole = Name(id='?', ctx="")
        if node.marked:
            return hole
        return super().generic_visit(node)

class SubtreeGeneration:
    def __init__(self, node: AST) -> None:
        self.cur_root = node
        self.subtrees = {}

    def collect_subtrees_util(self) -> list[AST]:
        todo = deque([(self.cur_root, 0)])
        visited = [self.cur_root]
        while todo:
            node, level = todo.popleft()
            for child in iter_child_nodes(node):
                if (not isinstance(child, operator) and (child not in visited)):
                    visited.append(child)
                    todo.append((child, level + 1))
                    self.subtrees[self.cur_root][level].append(child)
   
    def collect_subtrees(self):
        depth = self.depth(self.cur_root) - 1
        self.subtrees[self.cur_root] = [[] for _ in range(depth)] 
        self.collect_subtrees_util()
        return self.subtrees

    def pprint_subtrees(self):
            for node in self.subtrees:
                print("KEY: ", node)
                for idx, child in enumerate(self.subtrees[node]):
                    print(idx, child)

    def depth(self, node):
        return 1 + max(map(self.depth, iter_child_nodes(node)),
                   default = 0)

def copy_and_reduce(tree: AST, keep_list: list[AST]) -> AST:
    """ Copy tren & reduce nodes not in the keep_list. """

    # Mark every node not in keep_list.
    NodeMarker().visit(tree)
    for node in keep_list:
        node.marked = False
    
    # Copy tree and delete marked nodes.
    new_tree = copy.deepcopy(tree)
    NodeReducer().visit(new_tree)
    return new_tree

if __name__ == "__main__":
    tree = parse("1 + (2 + 3)")
    nodes = NodeCollector().collect(tree)

    # Ex: Remove level 1 of root (nodes[2]).
    subtreeGen = SubtreeGeneration(nodes[2])
    subtreeGen.collect_subtrees()
    subtrees = subtreeGen.subtrees
    for x in subtrees[nodes[2]][0]:
        nodes.remove(x)
    new_tree = copy_and_reduce(tree, nodes)
    print(unparse(new_tree))

    # Ex: Remove --> ? + (2 + 3)
    # nodes.remove(nodes[3])
    # empty_tree = copy_and_reduce(tree, nodes)
    # print(unparse(empty_tree))