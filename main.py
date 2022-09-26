# Inspired by: https://www.debuggingbook.org/beta/html/DeltaDebugger.html#Reducing-Failure-Inducing-Inputs
from ast import BinOp, Constant, iter_child_nodes, parse, unparse, operator, Name, NodeTransformer, NodeVisitor, AST
from collections import deque
import copy
from itertools import zip_longest
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

def compare_trees(t1, t2, del_list = []):
    if (type(t1) is not type(t2)):
        del_list.append(t1)
        return

    if isinstance(t1, AST):
        if (isinstance(t1, BinOp) and isinstance(t2, BinOp)) and (t1.op != t2.op):
            del_list.append(t1)
            return
        if (isinstance(t1, Constant) and isinstance(t2, Constant)) and (t1.value != t2.value):
            del_list.append(t1)
            return 
        if (isinstance(t1, Name) and isinstance(t2, Name)) and (t1.id != t2.id):
            del_list.append(t1)
            return 
        for k, v in vars(t1).items():
            if k in {"lineno", "end_lineno", "col_offset", "end_col_offset", "ctx"}:
                continue
            compare_trees(v, getattr(t2, k))   
    
    if isinstance(t1, list) and isinstance(t2, list):
        for n1, n2 in zip_longest(t1, t2):
            compare_trees(n1, n2)

    return del_list


if __name__ == "__main__":
    # tree = parse("1 + (2 + (1 + 0))")
    # tree2 = parse("1 + (2 + (1 + 1))")

    # tree = parse("str.split(sep)['a']")
    # tree2 = parse("str.split('-')['a']")

    # tree = parse("hello.split(sep)[0]")
    # tree2 = parse("str.split('a')[1]")

    tree = parse("str[0]")
    tree2 = parse("str[1:3]")


    print("For: ", unparse(tree), " AND ", unparse(tree2))
    del_list = compare_trees(tree, tree2)
    nodes = NodeCollector().collect(tree)
    # print("Length: ", len(nodes))
    for node in nodes: 
        if node in del_list:
            nodes.remove(node)
    # print("Length: ", len(nodes))
    new_tree = copy_and_reduce(tree, nodes)
    print(unparse(new_tree))


    

    # Ex: Remove level 1 of root (nodes[2]).
    # nodes = NodeCollector().collect(tree)
    # subtreeGen = SubtreeGeneration(nodes[2])
    # subtreeGen.collect_subtrees()
    # subtrees = subtreeGen.subtrees
    # for x in subtrees[nodes[2]][0]:
    #     nodes.remove(x)
    # new_tree = copy_and_reduce(tree, nodes)
    # print(unparse(new_tree))



    

    # Ex: Remove --> ? + (2 + 3)
    # nodes.remove(nodes[3])
    # empty_tree = copy_and_reduce(tree, nodes)
    # print(unparse(empty_tree))