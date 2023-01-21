
import ast
import copy

from typing import Any
from collections import OrderedDict, defaultdict
from itertools import zip_longest, combinations, groupby
from flask import Flask, jsonify, abort, make_response, render_template

# TODO: Turn into a classes. 
ID_COUNTER = 0
COLORS = ["#ccf1ff", "#E0D7FF", "#FFCCE1", "#D7EEFF", "#FAFFC7", "ffe5ec", "ffc2d1", "ffcaaf", "f1ffc4"]

class ReverseSketch:
    def __init__(self, sketch_id, sketch_AST, trees, holes, substitutions):
        self.id = sketch_id
        self.sketch_AST = sketch_AST
        self.trees = trees
        self.subs = substitutions
        # x_0, ... , x_n for each hole. 
        self.clickable_sketch = None
        self.holes = holes 
        self.parent_data = {}
        self.children = []

    '''
    Update the parent data. 
    @param 
    @return 
    '''
    def update_parent_data(self, sketch_id, hole_num, option_num):
        self.parent_data['sketch_id'] = sketch_id
        self.parent_data['hole_num'] = hole_num
        self.parent_data['option_num'] = option_num

    '''
    Does the parent meta data match a current parent object. 
    @param 
    @return 
    '''
    def matches_parent_data(self, sketch_id, hole_num, option_num):
        print(self.parent_data)
        return self.parent_data['sketch_id'] == sketch_id and self.parent_data['hole_num'] == hole_num and self.parent_data['option_num'] == option_num

    '''
    Update the children list. 
    @param 
    @return 
    '''
    def update_children(self, children):
        self.children.extend(children)

    '''
    Update the clickable sketch. 
    @param 
    @return 
    '''
    def update_clickable_sketch(self, clickable_sketch):
        self.clickable_sketch = clickable_sketch

    '''
    Find all of the original trees that have any of the substitutions. 
    @param 
    @return a list of original ASTs; the entire tree, not the subtree. 
    '''
    def recover_groups(self, hole_num: int, selected_hole_options: list[ast.AST]):
        print("Selected hole options: ", selected_hole_options)
        # Store the trees that satisfy that have the selected sub-expression. 
        valid_tree = []
        for tree_id, tree in enumerate(self.trees):
            # The substitution of the current tree for x_i. 
            tree_substitution = self.subs[tree_id][f"x_{hole_num}"]
            # If the substition is in the selected hole_options list, add it. 
            if tree_substitution in selected_hole_options:
                valid_tree.append(tree)
        # Return all of the valid trees. 
        return valid_tree

    '''
    Generate groups of candidate programs to color. 
    @param Hole number. 
    @return a dictionary of <sub,list[concrete programs]>
    '''
    def generate_groups(self, hole_num: int): 
        groups = dict()
        for tree_id, tree in enumerate(self.trees):
            hole_option_str = ast.unparse(self.subs[tree_id][f"x_{hole_num}"])
            groups.setdefault(hole_option_str, []).append(tree)
        return groups

    '''
    Expand a single hole. 
    @param 
    @return AST options for each hole. 
    '''
    def expand_hole(self, hole_num: int, see_groups: bool = False):
        # Global variable
        global ID_COUNTER
        # Generate the hole id based on the provided hole number. 
        hole_id = f"x_{hole_num}"
        print("Myself: ", self)
        # Array to store the options for the expanded hole. 
        hole_options = []
        # If there are not substitutions, this is a concrete program.
        print("Checking my subs: ", self.subs)
        if self.subs == [{}]:
            print("In here...")
            if see_groups: 
                to_return = {type(self.sketch_AST): [self]}, [self]
                print("To return: ", to_return)
                return to_return
            else:
                return [self]
        # There isn't a hole there anymore. 
        elif hole_id not in self.holes:
            print("Im in here!")
            # Generate a list of grouped programs and reverse sketches that represent the grouped programs. 
            group_dict, reverse_sketches = trees_uppper_bounds(self.trees)
             # Return the revrse sketches, and sometimes the grouped hole_options. 
            if see_groups:
                return group_dict, reverse_sketches
            else:
                return reverse_sketches
        # Traverse the list of trees.
        else: 
            for tree_id, tree in enumerate(self.trees): 
                # The substitution of the current tree for x_i. 
                print("Trying to get substitutions for: ", self)
                tree_substitution = self.subs[tree_id][hole_id]
                print("Tree substitution: ", tree_substitution, " for: ", self)
                # Add the substitution to the list of options.
                hole_options.append(tree_substitution) 
            # Generate a list of grouped programs and reverse sketches that represent the grouped programs. 
            group_dict, reverse_sketches = trees_uppper_bounds(hole_options)
            # Return the revrse sketches, and sometimes the grouped hole_options. 
            if see_groups:
                return group_dict, reverse_sketches
            else:
                return reverse_sketches
    
    '''
    Generate a string representation of each hole option. 
    @param 
    @return A list of lists of hole option strings. 
    '''
    def generate_hole_str(self):
        print(self.holes)
        # List of lists of hole AST options. 
        holes_ASTs = [self.expand_hole(hole_num) for hole_num in range(len(self.holes))]
        # String representations of hole optinos. 
        str_holes_ASTs = []
        # Iterate over each list, which represents the options for a single hole. 
        for hole_AST in holes_ASTs: 
            str_holes_ASTs.append([ast.unparse(x.sketch_AST) for x in hole_AST])
        return str_holes_ASTs

    '''
    Generate a JSON representation of the revere sketch.'
    @param 
    @return JSON representation of the reverse sketch.
    '''
    def generate_json(self):
        # return json.dumps(self.__dict__)
        return {
            'id': self.id,
            'sketch_str': f"{ast.unparse(self.sketch_AST)}",
            'holes': self.holes,
            'subs': self.generate_hole_str()
        }

    '''
    Generate a string representation of the revere sketch.'
    @param 
    @return string representation of the reverse sketch.
    '''
    def __str__(self):
        return f"{ast.unparse(self.sketch_AST)}"   

'''
Generate an AST with holes denoted by '?'
@param 
@return AST with holes denoted by '?'.
'''
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
        hole.is_hole = True
        if node.marked:
            # Increment id for next hole. 
            self.counter += 1
            return hole
        return super().generic_visit(node)

'''
Collect all of the nodes in an AST. 
@param AST that represents a single tree. 
@return a list of all the nodes in the AST.
'''
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

'''
Mark every node in the tree 'False'. 
@param root of tree to be marked. 
@return
'''
class TreeMarker(ast.NodeVisitor):
    def visit(self, node: ast.AST) -> ast.AST:
        node.marked = False
        return super().visit(node)

'''
Group trees by the type of the AST node. 
@param list of candidate program ASTS.
@return matrix of trees by type. 
'''
def group_trees_by_type(trees: list[ast.AST]) -> list[list[ast.AST]]:
    typed_lists = {}
    for tree in trees:
        # Parse body. 
        if (isinstance(tree, ast.Module)):
            print("Dictionary: ", tree.__dict__)
            if isinstance(tree.body[0], ast.FunctionDef):
                body: ast.AST = tree.body[0]
                print("Function body: ", body)
                expr = body
            else:
                body: ast.AST = tree.body[0]
                expr = body.__dict__['value']
        else:
            expr = tree

        if (isinstance(expr, ast.Name)):
            typed_lists.setdefault(f"Name-{ast.unparse(expr)}", []).append(tree) 
        elif (isinstance(expr, ast.Constant)):  
            typed_lists.setdefault(f"Constant-{ast.unparse(expr)}", []).append(tree) 
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

def antiunfy(trees):
    global ID_COUNTER
    '''
    Compare n ASTs
    @param single AST
    @paramr list of AST
    @return <head node, rest nodes>
    '''
    def compare_trees(head: ast.AST, rest: list[ast.AST], del_dict: OrderedDict[ast.AST, list[ast.AST]]):
        if not all(isinstance(t, type(head)) for t in rest):
            del_dict[head] = rest
            return del_dict

        if isinstance(head, ast.AST):
            if (isinstance(head, ast.Name) and any(isinstance(t, ast.Name) and (t.id != head.id) for t in rest)):
                del_dict[head] = rest
                return del_dict

            if (isinstance(head, ast.Constant) and any(isinstance(t, ast.Constant) and (t.value != head.value) for t in rest)):
                del_dict[head] = rest
                return del_dict

            if (isinstance(head, ast.Subscript) and (isinstance(t, ast.Subscript) for t in rest)):
                if type(head.__dict__['slice']) == ast.Slice and any(type(t.__dict__['slice']) != ast.Slice for t in rest):
                    del_dict[head] = rest
                    return del_dict

            for k,v in vars(head).items():
                if k in {"lineno", "end_lineno", "col_offset", "end_col_offset", "ctx", "marked"}:
                        continue
                # print("Here: ", v, head)
                compare_trees(v, list(map(lambda t: getattr(t, k), rest)), del_dict)

        if isinstance(head, list) and all(isinstance(t, list) for t in rest):
            for tups in zip_longest(head, *rest):
                compare_trees(tups[0], list(tups[1:]), del_dict)

        # Return statement. 
        return del_dict

    '''
    Generate substitutions for each AST. 
    @param list of ASTs
    @return <x1:?,..., xn:?>
    '''
    def generate_substitutions(del_dict: OrderedDict[ast.AST, list[ast.AST]]):
        # A list of substitutions for each tree.
        substitutions = []
        # Generate substitution for each tree.
        for tree_id, tree in enumerate(trees): 
            substitution = {}
            # Assign the current tree's ith hole to x_i. 
            for hole_id, k in enumerate(del_dict):
                # If the current tree is the first tree, the ith hole is the current key.
                if tree_id == 0: 
                    substitution[f"x_{hole_id}"] = k
                # Otherwise, it's the i-1 element of the current key.
                else:
                    substitution[f"x_{hole_id}"] = del_dict[k][tree_id-1]
            substitutions.append(substitution)
        return substitutions

    '''
    Mark the nodes to be deleted. 
    @param AST that represents a single tree.
    @return 
    '''
    def mark_nodes(tree: ast.AST, del_dict: OrderedDict[ast.AST, list[ast.AST]]):
        # Mark every node as 'False'.
        TreeMarker().visit(tree)
        nodes = TreeCollector().collect(tree)
        for node in del_dict: 
            # The index of a node to be deleted. 
            idx = nodes.index(node)
            # Mark the node 'True'. 
            nodes[idx].marked = True
        
    '''
    Generates generalization of n trees. 
    @param list of ASTs
    @return generalization of n trees. 
    '''
    def generate_generalizations(del_dict: OrderedDict[ast.AST, list[ast.AST]]): 
        # Mark the nodes that are going to be deleted in the head node.
        mark_nodes(trees[0], del_dict)
        # Generate a copy of the tree to the generalized. 
        generalized_tree = copy.deepcopy(trees[0])
        # Generate a generalization of the tree.  
        TreeGeneralizer(del_dict).visit(generalized_tree)
        # Return generalization.
        return generalized_tree

    #  Generate hole options.
    del_dict = compare_trees(trees[0], trees[1:], {})
    #  Generate holes.
    holes = [f"x_{i}" for i in range(len(del_dict))]
    #  Generate reverse sketch of group of trees. 
    reverse_sketch = generate_generalizations(del_dict)
    #  Genera substitutions for each tree in the group. 
    substitutions = generate_substitutions(del_dict)
    # (reverse sketch AST, substitutions for each tree)
    reverse_sketch_obj = ReverseSketch(ID_COUNTER, reverse_sketch, trees, holes, substitutions)
    # Update the id counter. 
    ID_COUNTER += 1
    return reverse_sketch_obj

'''
Anti-unify n trees. 
@param list of candidate program ASTS.
@return the most specific generalization of n trees. 
'''
def trees_uppper_bounds(trees: list[ast.AST]):
    # Group trees by root node type. 
    grouped_dict = group_trees_by_type(trees)
    # Anti-unify each group. 
    return grouped_dict, [antiunfy(group_items) for group, group_items in grouped_dict.items()]

'''
Expand a single hole.  
@param Reverse Sketch object.
@return sketches for the hole.
'''
def expand_hole(reverse_sketch_obj: ReverseSketch, hole_id):
    if reverse_sketch_obj.holes:
        # Reverse ksetches that can fill the selected hole. 
        hole_options = list(map(lambda x: ast.unparse(x.sketch_AST), reverse_sketch_obj.expand_hole(hole_id)))
        # print("Options: ", hole_options)
        return reverse_sketch_obj.expand_hole(hole_id)

'''
Read Python programs from a file. 
@param 
@return the most specific generalization of n trees. 
'''
def read_trees(file_name) -> list[ast.AST]:
    with open(file_name) as f:
        return [ast.parse(line.strip()) for line in f.readlines()]

'''
Read Python programs from a file. 
@param 
@return the most specific generalization of n trees. 
'''
def read_multi_line_trees():
    multi_line_trees = [
        """def foo():
        print("hello world")
        print("Working hard...")
        return 5
        """, 
        """def boo():
        return 6
        """
    ]
    trees = [ast.parse(tree) for tree in multi_line_trees]
    dumped = [ast.dump(tree) for tree in trees]
    unparsed = [ast.unparse(tree) for tree in trees]
    print("Unparsed: ", unparsed)
    return trees 


def interact(sketches: list[ReverseSketch]):
    print("Options: ")
    for sketch in sketches:
        print("\t", sketch)
    # Store the index of the sketch the user selected. 
    sketch_id = int(input(f"Pick sketch 0-{len(sketches)}: "))
    # Print the skecth the user selected.
    selected_sketch = sketches[sketch_id]
    print("Picked: ", selected_sketch)
    # Show the user the number of holes they can select from. 
    print("Holes: ", len(selected_sketch.holes))
    if (not len(selected_sketch.holes)):
        return
    # Store the selected hole. 
    hole_id = int(input(f"Which hole would you like to expand 0-{len(selected_sketch.holes)-1}: "))
    # Expand the selected hole.
    return interact(expand_hole(selected_sketch, hole_id))


app = Flask(__name__)

# Temporary memory structure; The array stores the JSON reps of the reverse sketches. 
# JSON representation of the original reverse sketches. 
REVERSE_SKETCHES_ORIGINAL = []
# Original reverse sketch class objects. 
REVERSE_SKETCHES_ORIGINAL_OBJS = []
# JSON representation of reverse sketch class objects. 
REVERSE_SKETCHES = []
# Reverse sketch class objects. 
REVERSE_SKETCHES_OBJS = []
# Previously viewed reverse sketch JSON representations. 
REVERSE_SKETCHES_HISTORY = []
# Previously viewed reverse sketch class objects. 
REVERSE_SKETCHES_HISTORY_OBJS = []
# The previously seen options. 
PREVIOUS_OPTIONS = []

'''
Generate a color map.
@param group dictionary <hole-option, list[concrete prorgams].
@return a dictionary <value, color>. 
'''
def generate_color_map(hole_groups_dict): 
    color_map = dict()
    hole_groups_list = list(hole_groups_dict)
    for idx, hole_option in enumerate(hole_groups_list):
        print("Idx: ", idx, hole_option)
        color_map.setdefault(hole_option, COLORS[idx])
    return color_map

'''
Generate a clickable sketch. 
@param ID
@return the ReverseObject with that ID.
'''
def createClickableSketch2(host, version, sketch_id, sketch, hold_idx):
    hole_counter = 0
    updated_sketch = "<td>"
    # Store the indices of the holes in the sketch. 
    for ch in sketch:
        if(ch == '?'):
            if (hole_counter == hold_idx):
                updated_sketch += f'</td><td><a class="selected-hole" href="{host}/oversynth/api/{version}/sketches/{sketch_id}/{hole_counter}">?</a></td><td>'
            else:
                updated_sketch += f'<a href="{host}/oversynth/api/v1.0/sketches/{sketch_id}/{hole_counter}">?</a>'
            hole_counter += 1
        else:
            updated_sketch += ch
    updated_sketch += "</td><td></td>"
    return updated_sketch

'''
Generate a clickable sketch. 
@param ID
@return the ReverseObject with that ID.
'''
def createClickableSketch(host, version, sketch_id, sketch):
    hole_counter = 0
    updated_sketch = ""
    # Store the indices of the holes in the sketch. 
    for ch in sketch:
        if(ch == '?'):
            updated_sketch += f'<a href="{host}/oversynth/api/{version}/sketches/{sketch_id}/{hole_counter}">?</a>'
            hole_counter += 1
        else:
            updated_sketch += ch
    return updated_sketch

'''
Generate a sketch with the hole option filled in. 
@param ID
@return more specific sketch with the hole number filled in.
'''
def createSketchWithFilledSpacedHole(host, version, hole_num, reverse_sketches, sketch_id, sketch, option_idx, option):
    hole_counter = 0
    updated_sketch = "<td>"
    # Store the indices of the holes in the sketch. 
    for ch in sketch:
        if(ch == '?'):
            if hole_counter == hole_num:
                print("checking options: ", reverse_sketches[option_idx].id)
                updated_sketch += f'</td><td><a href={host}/oversynth/api/{version}/sketches/{reverse_sketches[option_idx].id}/{hole_num}>{option}</a></td><td>'
                # updated_sketch += f'</td><td><a href={host}/oversynth/api/{version}/sketches/{sketch_id}/{hole_num}/{option_idx}>{option}</a></td><td>' 
            else: 
                updated_sketch += ch
            hole_counter += 1
        else:
            updated_sketch += ch
    updated_sketch += "</td>"
    print("Updated final: ", updated_sketch)
    return updated_sketch 

'''
Generate a sketch with the hole option filled in. 
@param ID
@return more specific sketch with the hole number filled in.
'''
def createSketchWithFilledHole(host, version, hole_num, sketch_id, sketch, option_idx, option):
    hole_counter = 0
    updated_sketch = ""
    # Store the indices of the holes in the sketch. 
    for ch in sketch:
        if(ch == '?'):
            if hole_counter == hole_num:
                updated_sketch += f'{option}'
                # Add space after the hole option to align all of the sketches.  
            else: 
                updated_sketch += ch
            hole_counter += 1
        else:
            updated_sketch += ch
    return updated_sketch 

'''
Update the string representation of the sketches. 
@param ID
@return sketch JSON representations with clickable holes.
'''
def updateJsonStringReps(host, version, JSON_obj): 
    return [createClickableSketch(host, version, obj['id'], obj['sketch_str']) for obj in JSON_obj]

'''
Generate a clickable options. 
@param ID
@return a list of clickable options.
'''
# def createClickableOptions2(host, version, option_sketches, options, sketch_id, hole_idx):
#     clickable_options = []
#     for option_idx, option in enumerate(options): 
#         updated_sketch = ""
#         # Store the indices of the holes in the sketch. 
#         for ch in option:
#             if(ch == '?'):
#                 for o in option_sketches:
#                     print("Looking at option sketches: ", o)
#                 print("Checking id of o: ", option_sketches[option_idx].id)
#                 print("to add: ", f'<a href={host}/oversynth/api/{version}/sketches/{option_sketches[option_idx].id}/{0}>{ch}</a>')
#                 updated_sketch += f'<a href={host}/oversynth/api/{version}/sketches/{option_sketches[option_idx].id}/{0}>{ch}</a>'
#                 print("updated sketch intermediate: ", updated_sketch)
#             else: 
#                 updated_sketch += ch
#         print("Final sketch: ", updated_sketch)
#         clickable_options.append(updated_sketch)
#     return clickable_options

'''
Generate a clickable options. 
@param ID
@return a list of clickable options.
'''
def createClickableOptions(host, version, options, sketch_id, hole_idx):
    clickable_options = []
    for option_idx, option in enumerate(options): 
        updated_sketch = ""
        # Store the indices of the holes in the sketch. 
        for ch in option:
            if(ch == '?'):
                updated_sketch += f'<a href={host}/oversynth/api/{version}/sketches/{sketch_id}/{hole_idx}/{option_idx}>{ch}</a>'
            else: 
                updated_sketch += ch
        print("Final sketch: ", updated_sketch)
        clickable_options.append(updated_sketch)
    return clickable_options

'''
Find the ReverseSketch object by ID.  
@param ID
@return the ReverseObject with that ID.
'''
def findObjByID(id: int) -> ReverseSketch:
    global REVERSE_SKETCHES_HISTORY_OBJS
    # print("Objects: ", REVERSE_SKETCHES_HISTORY_OBJS)
    for obj in REVERSE_SKETCHES_HISTORY_OBJS: 
        if obj.id == id:
            return obj
        # print("ID: ", obj.id, obj)
    return None

'''
Find the ReverseSketch JSON rep by ID.  
@param ID
@return the reverse sketch JSON with that ID.
'''
def findJsonByID(id: int): 
    global REVERSE_SKETCHES_HISTORY
    for obj in REVERSE_SKETCHES_HISTORY: 
        if obj['id'] == id: 
            return obj
    return None

'''
Find the ReverseSketch object by clickable sketch.  
@param ID
@return the ReverseObject with that clickable sketch.
'''
def findJsonByParentData(sketch_id: int, hole_id: int, option_num: int) -> ReverseSketch:
    global REVERSE_SKETCHES_HISTORY_OBJS
    for obj in REVERSE_SKETCHES_HISTORY_OBJS: 
        if obj.parent_data:
            if obj.matches_parent_data(sketch_id, hole_id, option_num):
                return obj
    return None

def print_json():
    global REVERSE_SKETCHES_HISTORY_OBJS
    for obj in REVERSE_SKETCHES_HISTORY_OBJS: 
        print("id: ", obj.id)
        print("sketch: ", ast.unparse(obj.sketch_AST))
        print("parent data: ", obj.parent_data)

'''
Find the length of the longest hole option.  
@param 
@return the length of the longest hole options.
'''
def get_length_of_longest_hole_option(hole_options):
    max_length = 0
    for option in hole_options:
        max_length = max(max_length, len(option))
    return max_length

'''
Print nested children utility.  
@param 
@return.
'''
def pretty_print_children_util(obj: ReverseSketch):
    """ return a family tree for a Person object """

    children = obj.children

    if not children:
        # this person has no children, recursion ends here
        return {'name': ast.unparse(obj.sketch_AST), 'children': []}

    # this person has children, get every child's family tree
    return {
        'name': ast.unparse(obj.sketch_AST),
        'children': [pretty_print_children_util(findObjByID(child)) for child in children],
    }

'''
Print nested children.  
@param 
@return.
'''
def pretty_print_children():
    print("Pretty Print!")
    overview = []
    for obj in REVERSE_SKETCHES_ORIGINAL_OBJS:
        family_tree = pretty_print_children_util(obj)
        overview.append(family_tree)
    print("Overview loook: ", overview)
    return overview

def generate_navigation(overview, html_overview = ""):
    html_overview += "<ul>"
    for family_tree in overview: 
        # Create
        # print("Family tree: ", family_tree)
        html_overview += f"<li><span class='caret'>{family_tree['name']}"
        html_overview += f"<ul class='nested'>"
        for child in family_tree['children']:
            if child['children']:
                generate_navigation(child, html_overview)
            else: 
                html_overview += f"<li>{child['name']}</li>"
        html_overview += "</ul>"
        html_overview += f"</li>"
    html_overview += "</ul>"
    return html_overview

# Routes.
@app.route('/oversynth/api/v1.0/sketches', methods=['GET'])
def get_sketches():
    global REVERSE_SKETCHES
    global REVERSE_SKETCHES_OBJS
    global REVERSE_SKETCHES_ORIGINAL
    # If reverse sketches is empty, populate with the highest-level sketches. 
    if not REVERSE_SKETCHES:
        # Host link.
        host = "http://127.0.0.1:5000/"
        # ASTs that represent the candidate programs.
        trees = read_trees("ex-input.txt")
        # Version 
        version = "v1.0"
        # Generate the reverse sketches. 
        _, reverse_sketches = trees_uppper_bounds(trees)
        # Store the original reverse sketches JSON representations. 
        REVERSE_SKETCHES_ORIGINAL.extend([obj.generate_json() for obj in reverse_sketches])
        # Store the original reverse sketches class objects. 
        REVERSE_SKETCHES_ORIGINAL_OBJS.extend([obj for obj in reverse_sketches])
        # Update the sketch history array by adding the current sketches 
        REVERSE_SKETCHES_HISTORY.extend([obj.generate_json() for obj in reverse_sketches])
        # Update the sketch history array by adding the current sketches Reverse Sketch class instance.  
        REVERSE_SKETCHES_HISTORY_OBJS.extend([obj for obj in reverse_sketches])
        # Set reverse sketches to a list of JSON objects for each reverse sketch. 
        REVERSE_SKETCHES_OBJS = [obj for obj in reverse_sketches]
        # Update the JSON representations to include sketches with clickable holes. 
        REVERSE_SKETCHES = [obj.generate_json() for obj in reverse_sketches]
        # Generate the clickable sketches.
        map(lambda sketch: sketch.update_clickable_sketch(createClickableSketch(host, version, sketch.id, ast.unparse(sketch.sketch_AST))), reverse_sketches)
        # PREVIOUS_OPTIONS.extend(list(map(lambda x: createClickableSketch(host, version, x.id, ast.unparse(x.sketch_AST)), reverse_sketches)))
        # Generate clickable sketches.
        clickable_sketches = updateJsonStringReps(host, version, REVERSE_SKETCHES_ORIGINAL)
        # Return a jsonified REVERSE_SKETCH.
        return render_template("home.html", sketches_len=len(REVERSE_SKETCHES), sketches=clickable_sketches)
    # If the reverse sketches are not empty, return them. 
    else: 
         # Return a jsonified REVERSE_SKETCH.
        return render_template("home.html", sketches_len=len(REVERSE_SKETCHES), sketches=REVERSE_SKETCHES)

@app.route('/oversynth/api/v1.0/sketches/<int:sketch_id>', methods=['GET'])
def get_sketch(sketch_id):
    global REVERSE_SKETCHES
    # If the reverse sketches are empty, abort. 
    if not len(REVERSE_SKETCHES) or len(REVERSE_SKETCHES) <= sketch_id:
        abort(404)
    # If the reverse sketches are not empty, return the sketch_id-th sketch. 
    return jsonify(REVERSE_SKETCHES[sketch_id])

@app.route('/oversynth/api/v1.0/sketches/<int:sketch_id>/<int:hole_id>', methods=['GET'])
def get_hole(sketch_id, hole_id):
    global REVERSE_SKETCHES
    global REVERSE_SKETCHES_HISTORY
    global REVERSE_SKETCHES_ORIGINAL
    global PREVIOUS_OPTIONS

    '''
    Generate new sketches that represent the sketch with a filled hole.   
    @param 
    @return A reverse sketch instance that represents the filled in sketch.
    '''
    def generate_new_sketches(selected_reverse_sketch, hole_num) -> list[ast.AST]:
        # Store the new sketches. 
        new_sketches = []
        # Retrieve the hole options for the selected hole. 
        group_dict, hole_options = selected_reverse_sketch.expand_hole(hole_num, see_groups=True)
        # This is a concrete program with no holes. 
        if len(hole_options) == 1: 
            sketch = hole_options[0]
            # Update the parent data. 
            parent_id = selected_reverse_sketch.id
            print("parent id: ", parent_id)
            print("cur parent data: ", sketch.parent_data)
            sketch.update_parent_data(parent_id, hole_num, 0)
            print("Parent info: ", sketch.parent_data)
            # Set teh concrete program to be the new reverse sketch. 
            new_sketches = [sketch]
            # Add the new sketch to the REVERSE SKETCHES. 
            REVERSE_SKETCHES_HISTORY_OBJS.extend(hole_options)
            # Update the sketch history array by adding the current sketches 
            REVERSE_SKETCHES_HISTORY.extend([obj.generate_json() for obj in hole_options])
        else:
            for option_num, hole_option in enumerate(hole_options):
                # print(f'{option_num}: {hole_option}')
                # Retrive all of the trees that have that hole option. 
                if (isinstance(hole_option.sketch_AST, ast.Name)):
                    selected_group = group_dict[f'Name-{ast.unparse(hole_option.sketch_AST)}']
                elif (isinstance(hole_option.sketch_AST, ast.Constant)):
                    selected_group = group_dict[f'Constant-{ast.unparse(hole_option.sketch_AST)}']
                else: 
                    selected_group = group_dict[list(group_dict)[option_num]]
                # Trees that have the selection option in the selected hole. 
                new_trees = selected_reverse_sketch.recover_groups(hole_num, selected_group)
                # Create new reverse sketches.
                _, new_reverse_sketches = trees_uppper_bounds(new_trees)
                # Update the clickable options. 
                for sketch in new_reverse_sketches:
                    # Update the parent data. 
                    sketch.update_parent_data(selected_reverse_sketch.id, hole_num, option_num)
                    print("Updating the parent data: ", sketch, sketch.parent_data)
                # Update the list of new sketches. 
                new_sketches.extend(new_reverse_sketches)
                # Add the new sketch to the REVERSE SKETCHES. 
                REVERSE_SKETCHES_HISTORY_OBJS.extend(new_sketches)
                # Update the sketch history array by adding the current sketches 
                REVERSE_SKETCHES_HISTORY.extend([obj.generate_json() for obj in new_sketches])
        print("New sketches: ", list(map(lambda x: x, new_sketches)))
        return new_sketches
   
    '''
    Generate a color map.   
    @param 
    @return.
    '''
    def generate_color_map(selected_reverse_sketch: ReverseSketch, hole_num):
        color_counter = 0 
        key_counter = 0
        color_key_map = dict()
        color_value_map = dict()
        group_dict, hole_options = selected_reverse_sketch.expand_hole(hole_num, see_groups=True)
        # If its a concrete program....
        if len(hole_options) > 1:
            for k,v in group_dict.items(): 
                # Assign the key color. 
                if (hole_options[key_counter] not in color_key_map):
                    color_key_map[ast.unparse(hole_options[key_counter].sketch_AST)] = COLORS[color_counter]
                # Assing each value a color. 
                for tree_id, tree in enumerate(selected_reverse_sketch.trees):
                    tree_substitution = selected_reverse_sketch.subs[tree_id][f"x_{hole_id}"]
                    if tree_substitution in v: 
                        color_value_map.setdefault(ast.unparse(tree), COLORS[color_counter])
                # Update hte counters for the hole options and the colors. 
                key_counter += 1
                color_counter += 1
        return color_key_map, color_value_map

    # Host link.
    host = "http://127.0.0.1:5000/"
    # Version 
    version = "v1.0"
    # JSON representation of the selected sketch. 
    selected_reverse_sketch_json = findJsonByID(sketch_id)
    # The Reverse Sketch class instance of the selected sketch. 
    selected_reverse_sketch = findObjByID(sketch_id)
    # If the reverse sketches are empty, abort. 
    if not len(REVERSE_SKETCHES) or not selected_reverse_sketch_json:
        abort(404)
    else: 
        # Create Reverse Sketches for the filled options. 
        new_reverse_sketches = generate_new_sketches(selected_reverse_sketch, hole_id)
        print("Got past here....")
        # Create filled and spaces hole options. 
        if len(new_reverse_sketches) == 1:
            filled_spaced_options = [ast.unparse(new_reverse_sketches[0].sketch_AST)]
            # Create an empty list for clickable options since there are no holes. 
            clickable_options = []
        else:
            filled_spaced_options: list[str] = [createSketchWithFilledSpacedHole(host, version, hole_id, new_reverse_sketches,sketch_id, selected_reverse_sketch_json['sketch_str'], option_idx, option) for option_idx, option in enumerate(selected_reverse_sketch_json['subs'][hole_id])]
            # Update the hole options so they're clickables
            clickable_options: list[str] = createClickableOptions(host, version, filled_spaced_options, sketch_id, hole_id)
        # Generate a clickable sketch of the current/selected reverse sketch. 
        clickable_selected_sketch = selected_reverse_sketch.clickable_sketch
        # Retrieve all of the option ids. 
        for option_num in range(len(filled_spaced_options)):
            print(sketch_id, hole_id, "Option_num: ", option_num)
        new_reverse_sketches_id = [findJsonByParentData(sketch_id, hole_id, option_num).id for option_num in range(len(filled_spaced_options))]
        # Update the selected sketch's children attribute. 
        selected_reverse_sketch.update_children(new_reverse_sketches_id)
        # Generate a color map. 
        color_value_map = {}
        _, color_value_map = generate_color_map(selected_reverse_sketch, hole_num=hole_id)
        # Pretty print the entire space of programs. 
        # overview_tree = pretty_print_children()
        overview_tree = []
        print("Overview: ", overview_tree)
        # html_overview = generate_navigation(overview_tree)
        html_overview = []
        # print("Html overview: ", html_overview)
        return render_template("options.html", 
                selected_sketch=createClickableSketch2(host, version, sketch_id, selected_reverse_sketch_json['sketch_str'], hole_id),
                options_len=len(clickable_options), 
                options=clickable_options, 
                prev_options_len=len(PREVIOUS_OPTIONS),
                prev_options=PREVIOUS_OPTIONS,
                len=len(selected_reverse_sketch.trees), 
                programs=color_value_map, 
                colors=COLORS, 
                history_len=len(REVERSE_SKETCHES_HISTORY),
                prev_sketches=updateJsonStringReps(host, version, REVERSE_SKETCHES_HISTORY),
                overview=html_overview)

# TODO: Change to PUT
@app.route('/oversynth/api/v1.0/sketches/<int:sketch_id>/<int:hole_num>/<int:option_num>', methods=['GET'])
def update_hole(sketch_id, hole_num, option_num):
    global REVERSE_SKETCHES
    global REVERSE_SKETCHES_OBJS
    global REVERSE_SKETCHES_HISTORY
    global REVERSE_SKETCHES_ORIGINAL

    '''
    Generate new sketches that represent the sketch with a filled hole.   
    @param 
    @return.
    '''
    def generate_new_sketches(selected_reverse_sketch):
        # Retrieve the hole options for the selected hole. 
        group_dict, hole_options = selected_reverse_sketch.expand_hole(hole_num, see_groups=True)
        # Retrieve trees that match the hole options.
        if (all(isinstance(x.sketch_AST, ast.Constant) for x in hole_options)):
            # Retrieve the selected constant.
            selected_constant = ((findJsonByID(sketch_id)['subs'])[hole_num])[option_num]
            # Find all of the hole options that equal that constant and update the selected group.
            selected_group = group_dict[f'Constant-{selected_constant}']
        else: 
            selected_group = group_dict[list(group_dict)[option_num]]
        return selected_group

    # Host link.
    host = "http://127.0.0.1:5000/"
    # Version 
    version = "v1.0"
    # JSON representation of the selected sketch. 
    selected_reverse_sketch_json = findJsonByID(sketch_id)
    # The Reverse Sketch class instance of the selected sketch. 
    selected_reverse_sketch = findObjByID(sketch_id)
    # 
    if len(REVERSE_SKETCHES) and selected_reverse_sketch:
        # Generate the selected group.
        selected_group = generate_new_sketches(selected_reverse_sketch)
        # Trees that have the selection option in the selected hole. 
        new_trees = selected_reverse_sketch.recover_groups(hole_num, selected_group)
        # Create new reverse sketches.
        _, new_reverse_sketches = trees_uppper_bounds(new_trees)
        # Store the class instance of the new reverse sketch. 
        new_reverse_sketch = new_reverse_sketches[0]
        # Generate JSON representation of the new reverse sketch. 
        new_reverse_sketch_json = new_reverse_sketch.generate_json()
        # Generate a clickable sketch of the new sketch. 
        clickable_new_reverse_sketch = createClickableSketch(host, version, new_reverse_sketch_json['id'], new_reverse_sketch_json['sketch_str'])
        # Pretty print the children. 
        print("New clickable reverse sketch: ", clickable_new_reverse_sketch)
        # pretty_print_children()
        # Update the sketch history array by adding the current sketches 
        REVERSE_SKETCHES_HISTORY.extend([obj.generate_json() for obj in new_reverse_sketches])
        # Update the sketch history array by adding the current sketches Reverse Sketch class instance.  
        REVERSE_SKETCHES_HISTORY_OBJS.extend([obj for obj in new_reverse_sketches])
        # Exrend the list Reverse Sketch class instances.  
        REVERSE_SKETCHES_OBJS = [obj for obj in new_reverse_sketches]
        # Extend the list of JSON objects that represent reverse sketches. 
        REVERSE_SKETCHES = [obj.generate_json() for obj in new_reverse_sketches]
        color_dict = dict()
        for tree in new_reverse_sketch.trees: 
            color_dict[ast.unparse(tree)] = COLORS[0]
        # Return the new skecth with programs that match it. 
        return render_template("options.html",
                selected_sketch=clickable_new_reverse_sketch,
                options_len=0, 
                options=[], 
                prev_options_len=0,
                prev_options=PREVIOUS_OPTIONS,
                len=len(new_reverse_sketch.trees), 
                programs=color_dict, 
                colors=COLORS, 
                history_len=len(REVERSE_SKETCHES_HISTORY),
                prev_sketches=updateJsonStringReps(host, version, REVERSE_SKETCHES_HISTORY))
    return jsonify(REVERSE_SKETCHES)  

@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404) 

if __name__ == "__main__":
    app.run(debug=True)