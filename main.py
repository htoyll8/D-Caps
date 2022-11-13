import ast
from itertools import zip_longest, combinations
from typing import Any
import copy
from flask import Flask, render_template

app = Flask(__name__)

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

class HoleCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        super().__init__()
        self.holes: list[ast.AST] = []

    def generic_visit(self, node: ast.AST) -> None:
        if (isinstance(node, ast.Name) and node.id == '?'):
            self.holes.append(node)
        return super().generic_visit(node)

    def collect(self, tree: ast.AST) -> list[ast.AST]: 
        # Reset nodes. 
        self.visit(tree)
        return self.holes

class TreeMarker(ast.NodeVisitor):
    def visit(self, node: ast.AST) -> ast.AST:
        node.marked = False
        return super().visit(node)

class TreeGeneralizer(ast.NodeTransformer):
    def __init__(self) -> None:
        self.holes = []

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
            # print("Retuning hole... ", type(node), ast.unparse(node), ast.unparse(hole))
            return hole
        return super().generic_visit(node)

class HoleInserter(ast.NodeTransformer):
    def __init__(self, to_insert) -> None:
        self.holes = []
        self.to_insert = to_insert

    def visit(self, node: ast.AST) -> Any:
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def visit_Module(self, node: ast.AST) -> Any:
        # Cannot remove modules.
        return super().generic_visit(node)
    
    def generic_visit(self, node: ast.AST) -> Any:
        if node.marked:
            # print("Retuning hole... ", type(node), ast.unparse(node))
            return self.to_insert
        return super().generic_visit(node)

def group_trees_by_type(trees):
    typed_lists = {}
    for tree in trees:
        # Parse body. 
        if (isinstance(tree, ast.Module)):
            body: ast.AST = tree.body[0]
            expr = body.__dict__['value']
        else:
            expr = tree

        if (isinstance(expr, ast.Name)):
            typed_lists.setdefault(ast.Name, []).append(tree) 
        elif (isinstance(expr, ast.Constant)):
            typed_lists.setdefault(f"Constant-{expr.kind}", []).append(tree) 
        elif (isinstance(expr, ast.BinOp)):
            typed_lists.setdefault(ast.BinOp, []).append(tree) 
        elif (isinstance(expr, ast.Index)):
            typed_lists.setdefault(ast.Index, []).append(tree) 
        elif (isinstance(expr, ast.Subscript)):
            if (type(expr.slice) == ast.Slice):
                typed_lists.setdefault(f"Subscript_{type(expr.slice)}", []).append(tree)
            else: 
                typed_lists.setdefault("Subscript_generic", []).append(tree)
        elif (isinstance(expr, ast.Call)):
            if (isinstance(expr.func, ast.Attribute)):
                typed_lists.setdefault(expr.func.attr, []).append(tree) 
            else: 
                typed_lists.setdefault(ast.Call, []).append(tree) 
        else: 
            typed_lists.setdefault(type(tree), []).append(tree)
    return typed_lists

def compare_trees(head: ast.AST, rest: list[ast.AST], del_dict: dict[ast.AST, list[ast.AST]]):
    # print("Comparing... ", ast.unparse(head), list(map(lambda x: ast.unparse(x), rest)))
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
            del_dict[head] = rest
            # print("Constant mismatch! ", ast.unparse(head), list(map(lambda x: ast.unparse(x), rest)))
            # print("Updated del_dict: ", list(map(lambda x: ast.unparse(x), del_dict[head])))
            return del_dict

        if (isinstance(head, ast.Subscript) and (isinstance(t, ast.Subscript) for t in rest)):
            if type(head.__dict__['slice']) == ast.Slice and any(type(t.__dict__['slice']) != ast.Slice for t in rest):
                # print("Slice mismatch! ", ast.unparse(head), head)
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

def generalize_tree(tree, del_dict):
    TreeMarker().visit(tree)
    tree_nodes = TreeCollector().collect(tree)
    for node in del_dict:
        idx = tree_nodes.index(node)
        tree_nodes[idx].marked = True
    head_tree_copy = copy.deepcopy(tree)
    TreeGeneralizer().visit(head_tree_copy)
    holes_loc = HoleCollector().collect(head_tree_copy)
    return head_tree_copy, ast.unparse(head_tree_copy), holes_loc

def insert_hole_sketch_util(reverse_sketch_ast, hole_idx):
    TreeMarker().visit(reverse_sketch_ast)

def insert_holes(reverse_sketch_ast, hole_sketches, hole_idx):
    hole_nodes = HoleCollector().collect(reverse_sketch_ast)
    tree_nodes = TreeCollector().collect(reverse_sketch_ast)
    for hole_sketch in hole_sketches:
        print("Inserting... ", hole_sketch)

def expand_holes_util(hole_options):
    grouped_dict = group_trees_by_type(hole_options)
    hole_sketches = []
    # Generalize typed group. 
    for _, group_items in grouped_dict.items():
        head, rest = group_items[0], group_items[1:]
        del_dict = compare_trees(head, rest, {})
        # Append all options if the group elements are constants. 
        if (isinstance(head, ast.Constant) and head in del_dict):
            hole_sketches.append(head)
            hole_sketches.extend(rest)
        #  Append generalizations of subsets of the hole options. 
        else: 
            reverse_sketch_ast, reverse_sketch, _ = generalize_tree(head, del_dict)
            hole_sketches.append(reverse_sketch_ast)
    return hole_sketches

def expand_holes(reverse_sketch_ast, del_dict):
    hole_idx = 0
    for hole_key in del_dict:
        hole_options = del_dict[hole_key]
        hole_options.insert(0, hole_key)
        hole_sketches = expand_holes_util(hole_options)
        print(f"Expanding hole {hole_idx}: ", list(map(lambda x: ast.unparse(x), hole_options)))
        print(f"Expanded sketches {hole_idx}: ", list(map(lambda x: ast.unparse(x), hole_sketches)))
        # insert_holes(reverse_sketch_ast, hole_sketches, hole_idx)
        hole_idx += 1
        
def trees_uppper_bounds(trees):
    print("Trees: ", list(map(lambda x: ast.unparse(x), trees)))
    print("======================================")
    # Group trees.
    grouped_dict = group_trees_by_type(trees)
    # Generalize typed group. 
    for _, group_items in grouped_dict.items():
        del_dict = compare_trees(group_items[0], group_items[1:], {})
        reverse_sketch_ast, reverse_sketch, _ = generalize_tree(group_items[0], del_dict)
        print("Reverse sketch: ", reverse_sketch)
        expand_holes(reverse_sketch_ast, del_dict)
        print("==================================")
    
def read_file(file_name) -> list[ast.AST]:
    with open(file_name) as f:
        return [ast.parse(line.strip()) for line in f.readlines()]

@app.route('/')
def hello_world(): 
    trees = [
        ast.parse("str[1:3]"),
        ast.parse("str[1:2]"),
        ast.parse("str[2:1]"),
        ast.parse("str.split(sep)[1:3]"),
        ast.parse("str.split(sep)[1:2]"),
        ast.parse("str.split(sep)[0]"),
        ast.parse("str.split(sep)[1]"),
        ast.parse("str.split(sep)[2]")
    ]   
    # trees = read_file('input-file.txt')\

if __name__ == "__main__":
    trees = [
        ast.parse("str[1:3]"),
        ast.parse("str[1:2]"),
        ast.parse("str[2:1]"),
        ast.parse("str.split(sep)[1:3]"),
        ast.parse("str.split(sep)[1:2]"),
        ast.parse("str.split(sep)[0]"),
        ast.parse("str.split(sep)[1]"),
        ast.parse("str.split(sep)[2]"),
        ast.parse("str.split(sep)[lo[1]]"),
        ast.parse("str.split(sep)[lo[2]]")
    ]

    # trees = read_file("input-file4.txt")
    trees_uppper_bounds(trees)
    


       