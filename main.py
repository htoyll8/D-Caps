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


def compare_trees(head, rest, del_list = []): 
    # All of the list element types are the same. 
    if not all(isinstance(t, type(head)) for t in rest):
        print("Types mismatch!", unparse(head), list(rest))
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
            if k in {"lineno", "end_lineno", "col_offset", "end_col_offset", "ctx"}:
                continue
            # print("K: ", k, " V: ", v, head, rest, new_rest)
            compare_trees(v, list(map(lambda t: getattr(t, k), rest)))
        
    if isinstance(head, list) and all(isinstance(t, list) for t in rest):
        for tups in zip_longest(head, *rest):
            # print("Tups: ", tups, tups[0], list(tups[1:]))
            compare_trees(tups[0], list(tups[1:]))
    
    return del_list


if __name__ == "__main__":
    # tree = parse("1 + (2 + (1 + 0))")
    # tree2 = parse("1 + (2 + (1 + 1))")

    # tree = parse("str.split(sep)['a']")
    # tree2 = parse("str.split('-')['a']")

    # tree = parse("hello.split(sep)[0]")
    # tree2 = parse("str.split('a')[1]")

    # tree = parse("str[0]")
    # tree2 = parse("str[1:3]")

    tree = parse("str.split(sep)[0]")
    tree2 = parse("str.split('-')[0]")
    tree3 = parse("string.split(str[4])[0]")
    tree4 = parse("str.split(sep)[0]")

    # tree = parse("1 + 2")
    # tree2 = parse("(1 + 2) + 2")
    # tree3 = parse("(1 + 3) + 2")
    # tree4 = parse("0 + 2")

    del_list = compare_trees(tree, [tree2, tree3, tree4])
    nodes = NodeCollector().collect(tree)
    for node in nodes: 
        if node in del_list:
            nodes.remove(node)
    new_tree = copy_and_reduce(tree, nodes)

    print("For: ", unparse(tree), unparse(tree2), unparse(tree3), unparse(tree4))
    print(unparse(new_tree))

    # del_list = compare_trees(tree, tree2)
    # print("For: ", unparse(tree), " AND ", unparse(tree2))
    # nodes = NodeCollector().collect(tree)
    # print(del_list)
    # print(nodes)
    # print("Length: ", len(nodes))
    # for node in nodes: 
    #     if node in del_list:
    #         print("Removing: ", node)
    #         nodes.remove(node)
    # print("Length: ", len(nodes))
    # new_tree = copy_and_reduce(tree, nodes)
    # print(unparse(new_tree))


    

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