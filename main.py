import ast
from itertools import zip_longest, combinations, groupby
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
            # print("Retuning hole... ", type(node), ast.unparse(node))
            return hole
        return super().generic_visit(node)


def group_trees_by_type(trees):
    typed_lists = {}
    for tree in trees:
        # Parse body. 
        body: ast.AST = tree.body[0]
        if (isinstance(body, ast.Expr)):
            print("Found expression!", body.__dict__['value'])
            expr = body.__dict__['value']
        
            if (isinstance(expr, ast.BinOp)):
                typed_lists.setdefault(ast.BinOp, []).append(tree) 
            elif (isinstance(expr, ast.Index)):
                typed_lists.setdefault(ast.Index, []).append(tree) 
            elif (isinstance(expr, ast.Slice)):
                typed_lists.setdefault(ast.Slice, []).append(tree) 
            elif (isinstance(expr, ast.Subscript)):
                typed_lists.setdefault(ast.Subscript, []).append(tree)
            elif (isinstance(expr, ast.Call)):
                if (isinstance(expr.func, ast.Attribute)):
                    typed_lists.setdefault(expr.func.attr, []).append(tree) 
                else: 
                    typed_lists.setdefault(ast.Call, []).append(tree) 
        else: 
            typed_lists.setdefault(type(tree), []).append(tree)
    return typed_lists


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

def main(trees):
    sketches = []
    grouped_trees_dict = group_trees_by_type(trees)
    for _, group_items in grouped_trees_dict.items():
        if (len(group_items) == 1):
            sketches.append(group_items[0])
        else: 
            del_dict = compare_trees(group_items[0], group_items[1:], {})
            print(del_dict)
    for sketch in sketches:
        print(ast.unparse(sketch))

if __name__ == "__main__":
    trees = [
        ast.parse("str.split(sep)[0]"),
        ast.parse("str.split(sep)[1]"),
        ast.parse("str.split('-')[0]"),
        ast.parse("str.split(lo[4])[0]"),
        ast.parse("str.split(lo[1])[0]"),
        ast.parse("str.split(lo[1])"),
        ast.parse("1 + 1")
    ]

    main(trees)