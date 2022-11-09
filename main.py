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
            # print("Retuning hole... ", type(node), ast.unparse(node))
            return hole
        return super().generic_visit(node)

def group_trees_by_type(trees):
    typed_lists = {}
    for tree in trees:
        # Parse body. 
        if (isinstance(tree, ast.Module)):
            body: ast.AST = tree.body[0]
            expr = body.__dict__['value']
        else:
            # print("Regular expression... ", type(tree))
            expr = tree

        # if (isinstance(body, ast.Expr)):
            # print("Found expression!", body.__dict__['value'])
            # expr = body.__dict__['value']
            
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
    holes_loc = HoleCollector().collect(head_tree_copy)
    return head_tree_copy, ast.unparse(head_tree_copy), holes_loc

def trees_uppper_bound_util(trees):
    head = trees[0]
    rest = list(trees[1:])
    del_dict = compare_trees(head, rest, {})
    # Compute hole options. 
    holes = []
    for k,v in del_dict.items():
        # options = list(map(lambda x: ast.unparse(x), v))
        # options.insert(0, ast.unparse(k))
        print("Ops: ", list(map(lambda x: ast.unparse(x), v)))
        options = v
        print("After setting options: ", options)
        options.insert(0, k)
        holes.append(options)
    # Reverse sketch and the memory location of each hole. 
    reverse_sketch_ast, reverse_sketch, holes_loc = generalize_tree(head, del_dict)
    print("Locations: ", holes_loc)
    print("Holes: ", holes)
    # Zip hole options with trees: 
    # Convert list of tuples into a dictionary.
    mem = {}
    str_asts = {}
    print("Holes: ", holes)
    for idx, options in enumerate(holes):
        option_dict = {}
        option_tups = list(zip(options, trees))
        for k, v in option_tups:
            k_str = ast.unparse(k)
            if k_str not in str_asts:
                str_asts[k_str] = k
            option_dict.setdefault(k_str, []).append(v)
        # Option dict with ASTs instead of strings. 
        for str, str_ast in str_asts.items():
            option_dict[str_ast] = option_dict.pop(str)
        mem.setdefault((f"num_{idx}", holes_loc[idx]), {}).update(option_dict)
    # Generalize holes.
    return reverse_sketch_ast, reverse_sketch, mem

def tree_upper_bound(trees): 
    sketch_dict = {}
    # Generate highest-level JSON.
    grouped_trees_dict = group_trees_by_type(trees)
    # print("Groups: ", grouped_trees_dict.values())
    hole_options = {}
    for _, group_items in grouped_trees_dict.items():
        # print("Items: ", list(map(lambda x: ast.unparse(x), group_items)))
        upper_bound_ast, upper_bound, option = trees_uppper_bound_util(group_items)
        hole_options.setdefault(upper_bound_ast, option)
        sketch_dict.setdefault(upper_bound_ast, group_items)
    return sketch_dict, hole_options

def present_trees(trees): 
    _, hole_options = tree_upper_bound(trees)
    reverse_sketches = list(hole_options.keys())
    for idx, reverse_sketch in enumerate(reverse_sketches):
        print(f"{idx}: {ast.unparse(reverse_sketch)}")
        for hole_count, hole_choices in hole_options[reverse_sketch].items():
            # print(f"K: {hole_count}, V: {hole_choices}")
            hole_choices_keys = list(hole_choices.keys())
            print("Trees: ", hole_choices_keys)
            print("Head: ", ast.unparse(hole_choices_keys[0]))
            print("Rest: ", list(map(lambda x: ast.unparse(x),hole_choices_keys[1:])))
            present_trees(hole_choices_keys)




        # for _, options in hole_options[reverse_sketch].items():
        #     print("Options: ", list(map(lambda x: ast.unparse(x), options.keys())))
            # new_reverse_sketches = list(options.keys())
            # _, new_hole_options = tree_upper_bound(new_reverse_sketches)
            # new_hole_options_str = list(map(lambda x: ast.unparse(x), list(new_hole_options.keys())))
            # print(f"New Hole options: {new_hole_options_str}")
   
    # print("Hole options: ", hole_options)
    # reverse_sketches = list(hole_options.keys())

    # # Present sketch options. 
    # print("Sketch options: ")
    # for idx, reverse_sketch in enumerate(reverse_sketches):
    #     print(f"{idx}: {reverse_sketch}")

    # # Ask user to pick a sketch. 
    # choosen_sketch_idx = int(input("Which sketch would you like to expand?"))
    # choosen_sketch = reverse_sketches[choosen_sketch_idx]
    # print(f"Expanding sketch: {choosen_sketch}")

    # # Get options for each hole. 
    # holes_idx = list(hole_options[choosen_sketch].keys())

    # Expand every hole. 
    # print("Holes: ", holes_idx)
    # for idx, hole in enumerate(holes_idx):
    #     hole_keys = list(hole_options[choosen_sketch][hole].keys())
    #     hole_keys_ast = list(map(lambda x: ast.parse(x), hole_keys)) #todo: this will be an isssue. 
    #     # print("Hole keys [pre-process]: ", hole_keys)
    #     sketch_dict, _ = tree_upper_bound(hole_keys_ast)
    #     for idx, new_hole in enumerate(list(sketch_dict.keys())):
    #         print(f"{idx}: {new_hole}")
    #     new_hole_choice = int(input("Which expansion?"))
    #     print("Picked: ", list(sketch_dict.keys())[new_hole_choice])
    #     print("============")
        

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

    trees = [
        ast.parse("str[1:3]"),
        ast.parse("str.split(sep)[1:3]"),
        ast.parse("str.split(sep)[0]"),
        ast.parse("str.split(sep)[1]"),
        ast.parse("str.split(sep)[lo[1]]"),
        ast.parse("str.split(sep)[lo[2]]")
    ]

    # trees = read_file("input-file.txt")
    present_trees(trees)
    

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


       