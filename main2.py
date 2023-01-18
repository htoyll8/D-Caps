
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
        self.holes = holes 

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
        # Array to store the options for the expanded hole. 
        hole_options = []
        # Traverse the list of trees.
        for tree_id, tree in enumerate(self.trees): 
            # The substitution of the current tree for x_i. 
            tree_substitution = self.subs[tree_id][hole_id]
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
def createSketchWithFilledHole(host, version, hole_num, sketch_id, sketch, option_idx, option, longest_hole_length):
    hole_counter = 0
    updated_sketch = "<td>"
    # Store the indices of the holes in the sketch. 
    for ch in sketch:
        if(ch == '?'):
            if hole_counter == hole_num:
                updated_sketch += f'</td><td><a href={host}/oversynth/api/{version}/sketches/{sketch_id}/{hole_num}/{option_idx}>{option}</a></td><td>'
                # Add space after the hole option to align all of the sketches.  
            else: 
                updated_sketch += ch
            hole_counter += 1
        else:
            updated_sketch += ch
    updated_sketch += "</td>"
    print("Updated final: ", updated_sketch)
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
def createClickableOptions(host, version, options, sketch_id, hole_idx):
    print("Option (in here): ", options)
    return [f'<a href={host}/oversynth/api/{version}/sketches/{sketch_id}/{hole_idx}/{option_idx}>{option}</a>' for option_idx, option in enumerate(options)]

'''
Find the ReverseSketch object by ID.  
@param ID
@return the ReverseObject with that ID.
'''
def findObjByID(id: int) -> ReverseSketch:
    global REVERSE_SKETCHES_HISTORY_OBJS
    print("Objects: ", REVERSE_SKETCHES_HISTORY_OBJS)
    for obj in REVERSE_SKETCHES_HISTORY_OBJS: 
        if obj.id == id:
            return obj
        print("ID: ", obj.id, obj)
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
Find the length of the longest hole option.  
@param 
@return the length of the longest hole options.
'''
def get_length_of_longest_hole_option(hole_options):
    max_length = 0
    for option in hole_options:
        max_length = max(max_length, len(option))
    return max_length

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
        trees = read_trees("input-file.txt")
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
        # Generare clickable sketches
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
    return render_template("option.html", sketches_len=len(REVERSE_SKETCHES), sketches=REVERSE_SKETCHES)

@app.route('/oversynth/api/v1.0/sketches/<int:sketch_id>/<int:hole_id>', methods=['GET'])
def get_hole(sketch_id, hole_id):
    global REVERSE_SKETCHES
    global REVERSE_SKETCHES_HISTORY
    global REVERSE_SKETCHES_ORIGINAL
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
        # Update the JSON representations to include sketches with clickable holes. 
        clickable_sketches = updateJsonStringReps(host, version, REVERSE_SKETCHES_ORIGINAL)
        # Retrieve the length of the longest substitution. 
        longest_hole_length = get_length_of_longest_hole_option(selected_reverse_sketch_json['subs'][hole_id])
        # Create filled hole options. 
        filled_options = [createSketchWithFilledHole(host, version, hole_id, sketch_id, selected_reverse_sketch_json['sketch_str'], option_idx, option, longest_hole_length) for option_idx, option in enumerate(selected_reverse_sketch_json['subs'][hole_id])]
        # Update the hole options so they're clickables
        clickable_options = createClickableOptions(host, version, filled_options, sketch_id, hole_id)
        # Retrieve the hole options for the selected hole. 
        group_dict, hole_options = selected_reverse_sketch.expand_hole(hole_id, see_groups=True)
        color_counter = 0 
        key_counter = 0
        color_key_map = dict()
        color_value_map = dict()
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
        # Return the options and concrete groups. 
        return render_template("options.html", sketches_len=len(clickable_sketches), 
                selected_sketch=createClickableSketch2(host, version, sketch_id, selected_reverse_sketch_json['sketch_str'], hole_id),
                # sketches=clickable_sketches, 
                options_len=len(clickable_options), 
                options=clickable_options, 
                len=len(selected_reverse_sketch.trees), 
                programs=color_value_map, 
                colors=COLORS, 
                history_len=len(REVERSE_SKETCHES_HISTORY),
                prev_sketches=updateJsonStringReps(host, version, REVERSE_SKETCHES_HISTORY))

# TODO: Change to PUT
@app.route('/oversynth/api/v1.0/sketches/<int:sketch_id>/<int:hole_num>/<int:option_num>', methods=['GET'])
def update_hole(sketch_id, hole_num, option_num):
    global REVERSE_SKETCHES
    global REVERSE_SKETCHES_OBJS
    global REVERSE_SKETCHES_HISTORY
    global REVERSE_SKETCHES_ORIGINAL
    # Host link.
    host = "http://127.0.0.1:5000/"
    # Version 
    version = "v1.0"
    # JSON representation of the selected sketch. 
    selected_reverse_sketch_json = findJsonByID(sketch_id)
    # The Reverse Sketch class instance of the selected sketch. 
    selected_reverse_sketch = findObjByID(sketch_id)
    if len(REVERSE_SKETCHES) and selected_reverse_sketch:
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
        new_trees = selected_reverse_sketch.recover_groups(hole_num, selected_group)
        # Create new reverse sketches.
        _, new_reverse_sketches = trees_uppper_bounds(new_trees)
        # Store the class instance of the new reverse sketch. 
        new_reverse_sketch = new_reverse_sketches[0]
        # Generate JSON representation of the new reverse sketch. 
        new_reverse_sketch_json = new_reverse_sketch.generate_json()
        # Update the sketch history array by adding the current sketches 
        REVERSE_SKETCHES_HISTORY.extend([obj.generate_json() for obj in new_reverse_sketches])
        # Update the sketch history array by adding the current sketches Reverse Sketch class instance.  
        REVERSE_SKETCHES_HISTORY_OBJS.extend([obj for obj in new_reverse_sketches])
        # Exrend the list Reverse Sketch class instances.  
        REVERSE_SKETCHES_OBJS = [obj for obj in new_reverse_sketches]
        # Exrend the list of JSON objects that represent reverse sketches. 
        REVERSE_SKETCHES = [obj.generate_json() for obj in new_reverse_sketches]
        # TODO (fix): Generate a color map. 
        color_dict = dict()
        for tree in new_reverse_sketch.trees: 
            color_dict[ast.unparse(tree)] = COLORS[0]
        # Return the new skecth with programs that match it. 
        return render_template("options.html",
                selected_sketch=createClickableSketch(host, version, new_reverse_sketch_json['id'], new_reverse_sketch_json['sketch_str']),
                options_len=0, 
                options=[], 
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