import ast
from itertools import zip_longest, combinations, product, starmap, groupby
from collections import OrderedDict
from typing import Any, AnyStr
import copy
from flask import Flask, render_template, redirect, url_for
from flask_restful import Api, Resource, reqparse, abort, fields, marshal_with
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
api = Api(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)

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
    def __init__(self, del_dict: dict[ast.AST, list[ast.AST]]) -> None:
        self.holes = []
        self.del_dict = del_dict
        self.counter = 0

    def visit(self, node: ast.AST) -> Any:
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def visit_Module(self, node: ast.AST) -> Any:
        # Cannot remove modules.
        return super().generic_visit(node)
    
    def generic_visit(self, node: ast.AST) -> Any:
        hole = ast.Name(id=f'?', ctx="")
        hole.hole_id = self.counter + 1
        if node.marked:
            for k,v in self.del_dict.items(): 
                if (is_equal(k, node)):
                    if all(isinstance(item, type(k)) for item in v):
                        common_type = extract_common_type(k)
                        hole = ast.Name(id=f'{common_type}?', ctx="")
            # Increment id for next hole. 
            self.counter += 1
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

def my_eval(tree):
    if isinstance(tree, ast.slice):
        return str
    elif isinstance(tree, ast.Subscript):
        return str
    elif isinstance(tree, ast.Index):
        return str
    elif isinstance(tree, ast.BinOp):
        return int 
    else: 
        return None

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

def is_equal(node1, node2):
    if type(node1) is not type(node2):
        return False
    if isinstance(node1, ast.AST):
        for k, v in vars(node1).items():
            if k in ('lineno', 'col_offset', 'ctx'):
                continue
            if not is_equal(v, getattr(node2, k)):
                return False
        return True
    elif isinstance(node1, list):
        return all(starmap(is_equal, zip(node1, node2)))
    else:
        return node1 == node2

def extract_common_type(a) -> str:
    if isinstance(a, ast.Constant):
        if isinstance(a.value, int): 
            return "int"
        elif isinstance(a.value, str):
            return "str"
        else: 
            return ""
    elif isinstance(a, ast.Name):
        print("Testing... here ", a.id)
        if isinstance(type(a.id), int):
            return "int"
        elif isinstance(type(a.id), str):
            return "str"
        else: 
            return ""
    else:
        print("Testing HERE... ", type(a))

def compare_trees(head: ast.AST, rest: list[ast.AST], del_dict: OrderedDict[ast.AST, list[ast.AST]]):
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
    TreeGeneralizer(del_dict).visit(head_tree_copy)
    holes_loc = HoleCollector().collect(head_tree_copy)
    return head_tree_copy, ast.unparse(head_tree_copy), holes_loc

def get_holes_from_user():
    lst = []
    n = int(input("Enter number of elements : "))
    for i in range(0, n):
        ele = int(input(f"{i}:"))
        lst.append(ele)
    return lst

# Return val: Options for each hole.
# Return type: list[list[AST]]
def get_hole_idxs(holes_dict, idxs):
    new_holes_list = []
    holes_list = list(holes_dict)
    for idx in idxs:
        hole_key = holes_list[idx]
        new_holes_list.append(holes_dict[hole_key])
    return new_holes_list

def expand_hole_util(to_expand_holes):
    expanded_holes = []
    for to_expand_hole in to_expand_holes:
        # print("To expand hole: ", list(map(lambda x: ast.unparse(x), to_expand_hole)))
        sketches = trees_uppper_bounds_no_expand(to_expand_hole)
        # print("Sketches: ", sketches)
        expanded_holes.append(sketches)
    return expanded_holes

# holes_dict: previous deletion dictionary.    
def expand_hole(sketch_ast, holes_dict):
    to_expand = get_holes_from_user()
    # Values of the holes (keys) to be expanded. 
    to_expand_holes = get_hole_idxs(holes_dict, to_expand)
    # Dictionary: <sketch, sub-expressions that match that sketch>
    expanded_holes = expand_hole_util(to_expand_holes)
    for expanded_hole in expanded_holes: 
        for k,v in expanded_hole.items(): 
            l = list(map(lambda x: ast.unparse(x), v))
            for el in l: 
                print(el)
            print("==========")
        print("======================================")

    # Subexpressions sketches generated from expanded holes. 
    holes = list(map(lambda x: list(x.keys()), expanded_holes))
    # for hole in holes: 
    #     for sketch in hole: 
    #         print("Sketch: ", sketch)
    #         to_expand = get_holes_from_user()
    return holes
    
def trees_uppper_bounds_no_expand(trees):
    # Group trees.
    grouped_dict = group_trees_by_type(trees)
    # Generalize typed group. 
    reverse_sketches = {}
    for _, group_items in grouped_dict.items():
        if (all(isinstance(x, ast.Constant) for x in group_items)):
            for item in group_items: 
                # reverse_sketches.setdefault(ast.unparse(item), []).append(item)
                reverse_sketches.setdefault(ast.unparse(item), []).append(item)
        else: 
            del_dict = compare_trees(group_items[0], group_items[1:], {})
            reverse_sketch_ast, reverse_sketch, _ = generalize_tree(group_items[0], del_dict)
            reverse_sketches.setdefault(reverse_sketch, []).extend(group_items)
    return reverse_sketches    

def trees_uppper_bounds(trees):
    # Group trees.
    grouped_dict = group_trees_by_type(trees)
    # Generalize typed group. 
    reverse_sketches = []
    for _, group_items in grouped_dict.items():
        del_dict = compare_trees(group_items[0], group_items[1:], {})
        reverse_sketch_ast, reverse_sketch, _ = generalize_tree(group_items[0], del_dict)
        reverse_sketches.append(reverse_sketch)
        # print("Printing del dict: ")
        # print_del_dict(del_dict)
        # for k,v in del_dict.items():
        #     print("Zipped: ", list(zip(list(map(lambda x: ast.unparse(x), v)), list(map(lambda x: ast.unparse(x), group_items[1:])))))
        #     print("Zipped: ", list(zip(v, group_items[1:])))
        print("Sketch: ", reverse_sketch)
        # if (del_dict):
        #     opts = expand_hole(reverse_sketch_ast, del_dict)
        #     print(opts)
    return grouped_dict, reverse_sketches

def find_intermediate_sketches(trees, hole=0):
    upperbound = trees_uppper_bounds_no_expand(trees)
    print(list(upperbound.keys())[0])

    intermediate_values = dict()
    for c in combinations(trees, 2):
        del_dict = compare_trees(c[0], c[1:], {})
        if del_dict:
            key = list(del_dict)[hole]
            updated_del_dict = { key: del_dict[key] }
            _, reverse_sketch, _ = generalize_tree(c[0], updated_del_dict)
            # print(reverse_sketch)
            intermediate_values.setdefault(reverse_sketch, []).extend(c)
    for inter in intermediate_values:
        print(inter)

def group_by_str(l):
    d = {}
    for el in l: 
        result = list(filter(lambda x: ast.unparse(el) == ast.unparse(x), list(d.keys())))
        # print("Unparsed: ", ast.unparse(el))
        if result: 
            d[result[0]].append(el)
        else: 
            d.setdefault(el, []).append(el)
    # print("Grouped by str: ", d)
    return d

def convert_tups_to_dict(l):
    res = {}
    for i in l:  
        res.setdefault(i[0],[]).append(i[1])
    # keys = res.keys()   
    # print(list(map(lambda x: ast.unparse(x), keys)))
    # group_by_str(keys)
    return res

def print_del_dict(del_dict):
    for k,v in del_dict.items():
        print("Key: ", ast.unparse(k))
        print("\t", list(map(lambda x: ast.unparse(x), v)))

def assign_sketch_colors(l):
    colors = ['AliceBlue', 'pink', 'Lavender', 'LightYellow', 'SandyBrown', 'HoneyDew']
    counter = 0
    new_l = []
    for sketch in l:
        new_l.append((colors[counter], sketch))
        counter += 1
    return new_l

def assign_colors(d):
    colors = ['AliceBlue', 'pink', 'Lavender', 'LightYellow', 'SandyBrown', 'HoneyDew']
    new_d = {}
    counter = 0
    for _, v in d.items():
        new_d[colors[counter]] = v
        counter += 1
    return new_d

def generate_color_tups(d, trees):
    new_l = []
    for tree in trees: 
        color = [k for k,v in d.items() if tree in v][0]
        new_l.append((color, ast.unparse(tree)))
    return new_l
    
def read_file(file_name) -> list[ast.AST]:
    with open(file_name) as f:
        return [ast.parse(line.strip()) for line in f.readlines()]

@app.route('/')
def main():
    trees = read_file("input-file2.txt")
    unparsed_trees = list(map(lambda x: ast.unparse(x), trees))
    groups, sketches = trees_uppper_bounds(trees)
    color_sketch_tups = assign_sketch_colors(sketches)
    color_dict = assign_colors(groups)
    color_trees_tups = generate_color_tups(color_dict, trees)
    print(color_trees_tups)
    return render_template("static/home.html", trees=color_trees_tups, sketches=color_sketch_tups)

if __name__ == "__main__":
    # app.run(debug=True)
    trees = [
        ast.parse("str.split(sep)[1:3]"),
        ast.parse("str[1:3]"),
        ast.parse("str[lo[1]:3]"),
        ast.parse("str[lo[2]:3]")
        # ast.parse("(str + str)[1:3]"),
        # ast.parse("(str + str1)[1:3]"),
        # ast.parse("(str2 + str)[1:3]"),
        # ast.parse("str[1:3]"),
        # ast.parse("str[1:len('a')]"),
        # ast.parse("str[1:len('b')]"),
        # ast.parse("str[2:1]"),
        # ast.parse("str.split(sep)[1:3]"),
        # ast.parse("str.split(sep)[1:2]"),
        # ast.parse("str.split(sep)[0]"),
        # ast.parse("str.split(sep)[1]"),
        # ast.parse("str.split(sep)[2]"),
        # ast.parse("str.split(sep)[lo[1]]"),
        # ast.parse("str.split(sep)[lo[2]]"),
    ]
    trees = read_file("input-file.txt")
    # groups, sketches = trees_uppper_bounds(trees)
    # find_intermediate_sketches(trees)
    trees_uppper_bounds(trees)
    # trees_uppper_bounds_new(trees, True)

    









































       