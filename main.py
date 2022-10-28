import ast
from itertools import zip_longest, combinations
from typing import Any
import copy
from click import option
from flask import Flask, render_template
from numpy import str_

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
            # print("Constant mismatch! ", ast.unparse(head), head)
            del_dict[head] = rest
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
    return ast.unparse(head_tree_copy)

def trees_uppper_bound_util(trees):
    head = trees[0]
    rest = list(trees[1:])
    del_dict = compare_trees(head, rest, {})
    # Compute hole options. 
    holes = []
    for k,v in del_dict.items():
        options = list(map(lambda x: ast.unparse(x), v))
        options.insert(0, ast.unparse(k))
        holes.append(options)
    # Zip hole options with trees: 
    # Convert list of tuples into a dictionary.
    mem = {}
    for idx, options in enumerate(holes):
        option_dict = {}
        option_tups = list(zip(options, trees))
        for k, v in option_tups:
            option_dict.setdefault(k, []).append(v)
        mem.setdefault(f"num_{idx}", {}).update(option_dict)
    # Generalize holes.
    upper_bound, _ = generalize_tree(head, del_dict), mem
    print("Upper bound: ", upper_bound)
    for mem_key in list(mem):
        hole_options = mem[mem_key]
        for c in combinations(hole_options.keys(), 2):
            values = list(map(lambda x: hole_options[x], c))
            make_head = values[0][0]
            make_head_remainder = values[0][1:]
            make_rest = values[1:][0]
            make_rest.extend(make_head_remainder)
            # String representation. 
            make_del_dict = compare_trees(make_head, make_rest, {})
            strRep = generalize_tree(make_head, make_del_dict)
            if (strRep != upper_bound):
                print(strRep)
    return generalize_tree(head, del_dict), mem

def tree_upper_bound(trees): 
    sketch_dict = {}
    # Generate highest-level JSON.
    grouped_trees_dict = group_trees_by_type(trees)
    # print("Groups: ", grouped_trees_dict.values())
    hole_options = {}
    for _, group_items in grouped_trees_dict.items():
        # print("Items: ", list(map(lambda x: ast.unparse(x), group_items)))
        upper_bound, option = trees_uppper_bound_util(group_items)
        hole_options.setdefault(upper_bound, option)
        sketch_dict.setdefault(upper_bound, group_items)
    return sketch_dict, hole_options

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
        # ast.parse("str.split(sep)[0]"),
        # ast.parse("str.split(sep)[1]"),
        # ast.parse("str.split(sep)[2]"),
        # ast.parse("str.split(sep)[lo[1]]"),
        # ast.parse("str.split(sep)[lo[2]]")
    ]

    upper_bound_dict, hole_options = tree_upper_bound(trees)
    for reverse_sketch,holes in hole_options.items():
        print(reverse_sketch, holes)
        print("\n")
    # picked_holes = {}
    # k = 'str.split(sep)[?]'
    # must_include = []
    # holes_count = len(hole_options[k])
    # while len(picked_holes) < holes_count:
    #     cur_holes = hole_options[k]
    #     hole_number = input(f"Holes [{holes_count} options]")
    #     picked_hole_options = cur_holes[f"num_{hole_number}"]
    #     for picked_hole_key, picked_hole_values in picked_hole_options.items():
    #         if (len(must_include)):
    #             if any(x in picked_hole_values for x in must_include):
    #                 print("Option: ", picked_hole_key)
    #             # print(list(map(lambda x: ast.unparse(x), picked_hole_values)))
    #         else:
    #             print("Option: ", picked_hole_key)  
    #     choice = input("Choice? ")
    #     picked_holes.setdefault(f"num_{hole_number}", choice)
    #     must_include = picked_hole_options[choice]
    #     print("Must include: ", list(map(lambda x: ast.unparse(x), must_include)))
    # print(picked_holes)


        
   

