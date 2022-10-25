import ast
from itertools import zip_longest, combinations, groupby
from typing import Any
import copy
from xxlimited import new

from numpy import isin

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
            # print("Found expression!", body.__dict__['value'])
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
            # print("Name mismatch! ", ast.unparse(head), head)
            del_dict[head] = rest
            return del_dict

        if (isinstance(head, ast.Constant) and any(isinstance(t, ast.Constant) and (t.value != head.value) for t in rest)):
            # print("Constant mismatch! ", ast.unparse(head), head)
            del_dict[head] = rest
            return del_dict

        if (isinstance(head, ast.Subscript) and (isinstance(t, ast.Subscript) for t in rest)):
            if any(type(head.__dict__['slice']) != type(t.__dict__['slice']) for t in rest):
                del_dict[head] = rest
                return del_dict

        for k,v in vars(head).items():
            if k in {"lineno", "end_lineno", "col_offset", "end_col_offset", "ctx", "marked"}:
                    continue
            # print("Here: ", v, head)
            compare_trees(v, list(map(lambda t: getattr(t, k), rest)), del_dict)

    if isinstance(head, list) and all(isinstance(t, list) for t in rest):
        for tups in zip_longest(head, *rest):
            # print("Here 1: ", tups)
            compare_trees(tups[0], list(tups[1:]), del_dict)

    # Return statement. 
    return del_dict

def unify_trees(trees):
    sketch_dict = {}
    for pair in combinations(trees, 2):
         # print("Pair... ", ast.unparse(pair[0]), ast.unparse(pair[1]))
         del_dict = compare_trees(pair[0], pair[1:], {})
         # Mark all nodes false. 
         TreeMarker().visit(pair[0])
         # Store nodes that won't be deleted.
         head_nodes = TreeCollector().collect(pair[0])
         # Mark nodes to delete as True and remove from head nodes.
         for node in del_dict: 
            idx = head_nodes.index(node)
            head_nodes[idx].marked = True
            head_nodes.remove(node)
         # Add holes to tree.  
         head_tree_copy = copy.deepcopy(pair[0])
         TreeGeneralizer().visit(head_tree_copy)
         head_tree_str = ast.unparse(head_tree_copy)
         sketch_dict.setdefault(head_tree_str, set()).update(pair)
    return sketch_dict

def read_file(file_name) -> list[ast.AST]:
    with open(file_name) as f:
        return [ast.parse(line.strip()) for line in f.readlines()]

def main(trees):
    sketches = []
    grouped_trees_dict = group_trees_by_type(trees)
    for _, group_items in grouped_trees_dict.items():
        if (len(group_items) == 1):
            sketches.append(ast.unparse(group_items[0]))
        else: 
            new_sketches = unify_trees(group_items)
            sketches.extend(list(new_sketches.keys()))
    return sketches

if __name__ == "__main__":
    # trees = [
    #     ast.parse("str.split(sep)[0]"),
    #     ast.parse("str.split(sep)[1]"),
    #     ast.parse("str.split('-')[0]"),
    #     ast.parse("str.split(lo[4])[0]"),
    #     ast.parse("str.split(lo[1])[0]"),
    #     ast.parse("str.split(lo[1])"),
    #     ast.parse("1 + 1")
    # ]

    trees = read_file('input-file.txt')
    reverse_sketches = main(trees)
    for sketch in reverse_sketches:
        print(sketch)