
import ast
import copy

from typing import Any
from collections import OrderedDict
from itertools import zip_longest, combinations, groupby
from flask import Flask, jsonify, abort, make_response, render_template

# TODO: Turn into a class. 
ID_COUNTER = 0

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
    Expand a single hole. 
    @param 
    @return AST options for each hole. 
    '''
    def expand_hole(self, hole_num: int, see_groups: bool = False):
        # Global variable
        global ID_COUNTER
        hole_id = f"x_{hole_num}"
        hole_options = []
        for tree_id, tree in enumerate(self.trees): 
            # The substitution of the current tree for x_i. 
            tree_substitution = self.subs[tree_id][hole_id]
            # Add the substitution to the list of options.
            hole_options.append(tree_substitution)
        # If all of the trees are constants, return their sketches.   
        if (all(isinstance(x, ast.Constant) for x in hole_options)):
            sketches = []
            seen_sketches = set()
            for x in hole_options:
                x_str = ast.unparse(x)
                # If we haven't seen this value create a reverse sketch of it. 
                if x_str not in seen_sketches: 
                    seen_sketches.add(x_str)
                    sketches.append(ReverseSketch(ID_COUNTER, x, [], [], []))
                    # Increment the ID counter. 
                    ID_COUNTER += 1
            if see_groups: 
                return {"Consts" : hole_options}, sketches
            else: 
                return sketches
        # Return the reverse sketches, and sometimes groups. 
        group_dict, reverse_sketches = trees_uppper_bounds(hole_options)
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
# JSON representation of reverse sketch class objects. 
REVERSE_SKETCHES = []
# Reverse sketch class objects. 
REVERSE_SKETCHES_OBJS = []
# Previously viewed reverse sketch JSON representations. 
REVERSE_SKETCHES_HISTORY = []

'''
Generate a clickable sketch. 
@param ID
@return the ReverseObject with that ID.
'''
def createClickableSketches(host, sketch_id, sketch):
    hole_counter = 0
    updated_sketch = ""
    # Store the indices of the holes in the sketch. 
    for ch in sketch:
        if(ch == '?'):
            updated_sketch += f'<a href="{host}/oversynth/api/v1.0/sketches/{sketch_id}/{hole_counter}">?</a>'
            hole_counter += 1
        else:
            updated_sketch += ch
    print("Updated sketch: ", updated_sketch)
    return updated_sketch

'''
Update the string representation of the sketches. 
@param ID
@return sketch JSON representations with clickable holes.
'''
def updateJsonStringReps(host): 
    global REVERSE_SKETCHES
    return [createClickableSketches(host, obj['id'], obj['sketch_str']) for obj in REVERSE_SKETCHES]


'''
Generate a clickable options. 
@param ID
@return a list of clickable options.
'''
def createClickableOptions(host, obj, sketch_id, hole_idx):
    return [f'<a href={host}/oversynth/api/v1.0/sketches/{sketch_id}/{hole_idx}/{option_idx}>{option}</a>' for option_idx, option in enumerate(obj['subs'][hole_idx])]

# '''
# Update the string representation of the options. 
# @param ID
# @return sketch JSON representations with clickable holes.
# '''
# def updateJsonOptionReps(host): 
#     global REVERSE_SKETCHES
#     clickable_subs = []
#     for obj in REVERSE_SKETCHES:
#         holes_count = len(obj['subs'])
#         sketch_id = obj['id']
#         for hole_idx in range(holes_count):
#              clickable_subs.append([f'<a href={host}/oversynth/api/v1.0/sketches/{sketch_id}/{hole_idx}/{option_idx}>{option}</a>' for option_idx, option in enumerate(obj['subs'][hole_idx])])
#     return clickable_subs

'''
Find the ReverseSketch object by ID.  
@param ID
@return the ReverseObject with that ID.
'''
def findObjByID(id: int) -> ReverseSketch:
    global REVERSE_SKETCHES_OBJS
    print("Objects: ", REVERSE_SKETCHES_OBJS)
    for obj in REVERSE_SKETCHES_OBJS: 
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
    global REVERSE_SKETCHES
    for obj in REVERSE_SKETCHES: 
        if obj['id'] == id: 
            return obj
    return None

'''
Find all of the constants that match the selected one.   
@param ID
@return a list of ASTs that equal the constant. 
'''
def findConstants(selected_option: str, hole_options: list[ast.AST]):
    new_hole_options = []
    for option in hole_options:
        if (ast.unparse(option) == selected_option):
            new_hole_options.append(option)
    return new_hole_options

# Routes.
@app.route('/oversynth/api/v1.0/sketches', methods=['GET'])
def get_sketches():
    global REVERSE_SKETCHES
    global REVERSE_SKETCHES_OBJS
    # If reverse sketches is empty, populate with the highest-level sketches. 
    if not REVERSE_SKETCHES:
        trees = read_trees("ex-input.txt")
        # Generate the reverse sketches. 
        _, reverse_sketches = trees_uppper_bounds(trees)
        REVERSE_SKETCHES_OBJS = [obj for obj in reverse_sketches]
        # Set reverse sketches to a list of JSON objects for each reverse sketch. 
        REVERSE_SKETCHES = [obj.generate_json() for obj in reverse_sketches]
        # Update the JSON representations to include sketches with clickable holes. 
        clickable_sketches = updateJsonStringReps("http://127.0.0.1:5000/")
        # Return a jsonified REVERSE_SKETCH.
        return render_template("home.html", sketches_len=len(REVERSE_SKETCHES), sketches=clickable_sketches)
        return jsonify(REVERSE_SKETCHES)
    # If the reverse sketches are not empty, return them. 
    else: 
         # Return a jsonified REVERSE_SKETCH.
        return render_template("home.html", sketches_len=len(REVERSE_SKETCHES), sketches=REVERSE_SKETCHES)
        return jsonify(REVERSE_SKETCHES)

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
    # If the reverse sketches are empty, abort. 
    selected_reverse_sketch_json = findJsonByID(sketch_id)
    selected_reverse_sketch = findObjByID(sketch_id)
    if not len(REVERSE_SKETCHES) or not selected_reverse_sketch_json:
    # if not len(REVERSE_SKETCHES) or len(REVERSE_SKETCHES[sketch_id]['subs']) <= hole_id:
        abort(404)
    # Update the JSON representations to include sketches with clickable holes. 
    clickable_sketches = updateJsonStringReps("http://127.0.0.1:5000/")
    # Update the hole options so they're clickable.
    clickable_options = createClickableOptions("http://127.0.0.1:5000/", selected_reverse_sketch_json, sketch_id, hole_id)
    # If the reverse sketches are not empty, return the sketch_id-th sketch. 
    return render_template("options.html", sketches_len=len(clickable_sketches), sketches=clickable_sketches, options_len=len(clickable_options), options=clickable_options, len = len(selected_reverse_sketch.trees), Programs = [ast.unparse(x) for x in selected_reverse_sketch.trees])
    # return render_template("options.html", sketches_len=len(clickable_sketches), sketches=clickable_sketches, options_len=len(selected_reverse_sketch_json['subs'][hole_id]), options=selected_reverse_sketch_json['subs'][hole_id], len = len(selected_reverse_sketch.trees), Programs = [ast.unparse(x) for x in selected_reverse_sketch.trees])
    # return jsonify(REVERSE_SKETCHES[sketch_id]['subs'][hole_id])

# TODO: Change to PUT
@app.route('/oversynth/api/v1.0/sketches/<int:sketch_id>/<int:hole_num>/<int:option_num>', methods=['GET'])
def update_hole(sketch_id, hole_num, option_num):
    global REVERSE_SKETCHES
    global REVERSE_SKETCHES_OBJS
    global REVERSE_SKETCHES_HISTORY

    selected_reverse_sketch = findObjByID(sketch_id)

    if len(REVERSE_SKETCHES) and selected_reverse_sketch:
        # Retrieve the reverse sketch object that matches the id. 
        print("Selected reverse sketch: ", selected_reverse_sketch)
        print("Selected hole: ", hole_num)
        print("Selected option: ", option_num)

        # Retrieve the hole options for the selected hole. 
        group_dict, hole_options = selected_reverse_sketch.expand_hole(hole_num, see_groups=True)
        print("Group dictionary: ", group_dict)
        print("Hole options: ", hole_options)
        print("Hole options: ", list(map(lambda x: ast.unparse(x.sketch_AST), hole_options)))

        # Retrieve trees that match the hole options.
        if (all(isinstance(x.sketch_AST, ast.Constant) for x in hole_options)):
            print("In here...")
            selected_group = group_dict[list(group_dict)[0]]
            print("Selected group here: ", selected_group)
            selected_constant = ((findJsonByID(sketch_id)['subs'])[hole_num])[option_num]
            print("Selected constant: ", selected_constant)
            # Find all of the hole options that equal that constant and update the selected group.
            selected_group = findConstants(selected_constant, selected_group)
        else: 
            selected_group = group_dict[list(group_dict)[option_num]]
        new_trees = selected_reverse_sketch.recover_groups(hole_num, selected_group)
        print("Selected group: ", selected_group)
        

        # Create new reverse sketches.
        _, new_reverse_sketches = trees_uppper_bounds(new_trees)
        print("Reverse sketches: ", list(map(lambda x: ast.unparse(x.sketch_AST), new_reverse_sketches)))
        REVERSE_SKETCHES_OBJS = [obj for obj in new_reverse_sketches]
        REVERSE_SKETCHES = [obj.generate_json() for obj in new_reverse_sketches]
        # Update the JSON representations to include sketches with clickable holes. 
        clickable_sketches = updateJsonStringReps("http://127.0.0.1:5000/")
        # return jsonify(REVERSE_SKETCHES)
        return render_template("index.html", len = len(new_reverse_sketches[0].trees), Programs = [ast.unparse(x) for x in new_reverse_sketches[0].trees], sketches_len= len(clickable_sketches), sketches=clickable_sketches)
    return jsonify(REVERSE_SKETCHES)    

@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404) 

if __name__ == "__main__":
    app.run(debug=True)
    # trees = read_trees("input-file.txt")
    # reverse_sketches = trees_uppper_bounds(trees)
    # interact(reverse_sketches)
    # First reverse sketch. 
    # test_sketch = reverse_sketches[0]
    # print(ast.unparse(test_sketch.sketch_AST))
    # # for hole_id in range(len(test_sketch.holes)):
    # test_sketches2 = expand_hole(test_sketch, 0)
    # expand_hole(test_sketches2[1], 0)
