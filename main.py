# Inspired by: https://www.debuggingbook.org/beta/html/DeltaDebugger.html#Reducing-Failure-Inducing-Inputs
from ast import BinOp, Constant, iter_child_nodes, parse, unparse, operator, Name, NodeTransformer, NodeVisitor, AST
from collections import deque
import copy
from itertools import zip_longest
import itertools
from typing import Any, List

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

class NodeUnmarker(NodeVisitor):
    def visit(self, node: AST) -> AST:
        node.marked = False
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
   
    def collect_subtrees(self) -> list[list[AST]]:
        depth = self.depth(self.cur_root) - 1
        self.subtrees[self.cur_root] = [[] for _ in range(depth)] 
        self.collect_subtrees_util()
        return self.subtrees

    def pprint_subtrees(self) -> None:
            for node in self.subtrees:
                print("KEY: ", node)
                for idx, child in enumerate(self.subtrees[node]):
                    print(idx, child)

    def depth(self, node) -> int:
        return 1 + max(map(self.depth, iter_child_nodes(node)),
                   default = 0)

def copy_and_reduce(tree: AST, keep_list: list[AST]) -> AST:
    """ Copy & reduce nodes not in the keep_list. """

    # Mark every node not in keep_list.
    NodeMarker().visit(tree)
    for node in keep_list:
        node.marked = False
    
    # Copy tree and delete marked nodes.
    new_tree = copy.deepcopy(tree)
    NodeReducer().visit(new_tree)
    return new_tree

def compare_trees(head: AST, rest: list[AST], del_list: list[AST] = []) -> list[AST]: 
    # All of the list element types are the same. 
    if not all(isinstance(t, type(head)) for t in rest):
        # print("Types mismatch!", unparse(head), list(rest))
        del_list.append(head)
        return 

    if isinstance(head, AST):
        if (isinstance(head, BinOp) and all(isinstance(t, BinOp) for t in rest)) and (not all((t.op == head.op) for t in rest)):
            del_list.append(head)
            return 
        if (isinstance(head, Constant) and all(isinstance(t, Constant) for t in rest)) and (not all((t.value == head.value) for t in rest)):
            del_list.append(head)
            return 
        if (isinstance(head, Name) and all(isinstance(t, Name) for t in rest)) and (not all((t.id == head.id) for t in rest)):
            del_list.append(head)
            return 
        for k, v in vars(head).items():
            if k in {"lineno", "end_lineno", "col_offset", "end_col_offset", "ctx", "marked"}:
                continue
            # print("K: ", k, " V: ", v, head, rest, new_rest)
            compare_trees(v, list(map(lambda t: getattr(t, k), rest)), del_list)
        
    if isinstance(head, list) and all(isinstance(t, list) for t in rest):
        for tups in zip_longest(head, *rest):
            # print("Tups: ", tups, tups[0], list(tups[1:]))
            compare_trees(tups[0], list(tups[1:]), del_list)
    
    return del_list

def unify(head: AST, rest: list[AST]) -> list[AST]:
    del_list = compare_trees(head, rest, [])  
    nodes = NodeCollector().collect(head)
    for node in nodes: 
        if node in del_list:
            nodes.remove(node)
    return copy_and_reduce(head, nodes)

def generate_partitions(trees: list[AST]) -> dict:
    match_table = {}
    upper_bound = unparse(unify(trees[0], list(trees[1:])))
    print("Upper bound: ", upper_bound)

    # for L in range(2, len(trees) + 1):
    for L in range(2, 3):
        print(L)
        for subset in itertools.combinations(trees, L):
            # print("Unifying... ", unparse(subset[0]), list(map(lambda t: unparse(t), subset[1:])))
            new_tree = unparse(unify(subset[0], list(subset[1:])))
            if new_tree not in match_table: 
                # print("Adding... ", new_tree)
                match_table[new_tree] = []
            match_table[new_tree].append(subset)
            # print(unparse(new_tree), " for ", unparse(subset[0]), list(map(lambda t: unparse(t), subset[1:])))
    return match_table

def read_file(file_name) -> list[AST]:
    with open(file_name) as f:
        return [parse(line.strip()) for line in f.readlines()]


if __name__ == "__main__":
    # trees = [
    #     parse("str.split(sep)[0]"),
    #     parse("str.split(sep)[1]"),
    #     parse("str.split('-')[0]"),
    #     parse("string.split(lo[4])[0]"),
    #     parse("str[0:3]"),
    #     parse("str.split(lo[1])[0]")
    # ]

    # match_table = generate_partitions(trees)
    
    trees = read_file("input-file.txt")
    match_table = generate_partitions(trees)
    for k in match_table.keys():
        print(k)
    