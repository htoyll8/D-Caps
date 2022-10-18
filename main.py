import ast
from itertools import zip_longest, combinations, groupby
from math import comb
from typing import Any
import copy

class TreeCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        super().__init__()
        self.nodes: list[ast.AST] = []

    def generic_visit(self, node: ast.AST) -> None:
        self.nodes.append(node)
        return super().generic_visit(node)

    def collect(self, tree: ast.AST) -> list[ast.AST]: 
        # Reset nodes. 
        self.visit(tree)
        return self.nodes


class TreeMarker(ast.NodeVisitor):
    def visit(self, node: ast.AST) -> ast.AST:
        node.marked = False
        return super().visit(node)


class TreeGeneralizer(ast.NodeTransformer):
    def visit(self, node: ast.AST) -> Any:
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def visit_Module(self, node: ast.AST) -> Any:
        # Cannot remove modules.
        return super().generic_visit(node)
    
    def generic_visit(self, node: ast.AST) -> Any:
        hole = ast.Name(id='?', ctx="")
        if node.marked:
            print("Retuning hole... ", type(node), ast.unparse(node))
            return hole
        return super().generic_visit(node)


def partition_trees(t):
    typed_lists = [list(v) for i, v in groupby(t, lambda x: type(x))] 
    hole_options = {}
    print("Typed lists: ", typed_lists)
    for l in typed_lists:
        if (len(l) > 1):
            for c in combinations(l, 2):
                # print("C: ", c)
                del_dict = compare_trees(c[0], c[1:], {})
                TreeMarker().visit(c[0])
                for node in TreeCollector().collect(c[0]):
                    if node in del_dict.keys():
                        node.marked = True
                tree_copy = copy.deepcopy(c[0])
                TreeGeneralizer().visit(tree_copy)
                prog_str = ast.unparse(tree_copy)
                if (prog_str not in hole_options):
                    hole_options[prog_str] = set()
                hole_options[prog_str].update(c)
                # print("Tree after antiunification: ", ast.unparse(tree_copy))
        elif len(l) == 1: 
            # Only element... add to hole options. 
            prog_str = ast.unparse(l[0])
            if (prog_str not in hole_options):
                hole_options[prog_str] = set()
            hole_options[prog_str].add(l[0])
    print("Hole options: ", hole_options)
       

def compare_trees(head: ast.AST, rest: list[ast.AST], del_dict: dict[ast.AST, list[ast.AST]]):
    # print("Comparing... ", head, rest)
    if not all(isinstance(t, type(head)) for t in rest):
        # print("Mismatch! ", ast.unparse(head))
        del_dict[head] = rest
        return del_dict

    if isinstance(head, ast.AST):
        if (isinstance(head, ast.Name) and any(isinstance(t, ast.Name) and (t.id != head.id) for t in rest)):
            # print("Name mismatch! ", ast.unparse(head))
            del_dict[head] = rest
            return del_dict

        if (isinstance(head, ast.Constant) and any(isinstance(t, ast.Constant) and (t.value != head.value) for t in rest)):
            # print("Constant mismatch! ", ast.unparse(head))
            del_dict[head] = rest
            return del_dict

        for k,v in vars(head).items():
            if k in {"lineno", "end_lineno", "col_offset", "end_col_offset", "ctx", "marked"}:
                    continue
            compare_trees(v, list(map(lambda t: getattr(t, k), rest)), del_dict)

    if isinstance(head, list) and all(isinstance(t, list) for t in rest):
        for tups in zip_longest(head, *rest):
            compare_trees(tups[0], list(tups[1:]), del_dict)

    # Return statement. 
    return del_dict
        

def main(t):
    partition_trees(t)

    del_dict = compare_trees(t[0], t[1:], {})
    for k in del_dict:
        # print("Delection dictionary... ", del_dict)
        partition_trees(del_dict[k])

if __name__ == "__main__":
    trees = [
        ast.parse("str.split(sep)[0]"),
        ast.parse("str.split(sep)[1]"),
        ast.parse("str.split('-')[0]"),
        ast.parse("str.split(lo[4])[0]"),
        ast.parse("str.split(lo[1])[0]")
    ]

    main(trees)