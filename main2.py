
import ast
import copy

from typing import Any
from collections import OrderedDict
from itertools import zip_longest, combinations, groupby

class ReverseSketch:
    def __init__(self, sketch_AST, trees, holes, substitutions):
        self.sketch_AST = sketch_AST
        self.trees = trees
        self.holes = holes
        self.subs = substitutions

    # Expand a single hole. 
    def expand_hole(self, hole_num: int):
        hole_id = f"x_{hole_num}"
        hole_options = []
        for tree_id, tree in enumerate(self.trees): 
            # The substitution of the current tree for x_i. 
            tree_substitution = self.subs[tree_id][hole_id]
            # Add the substitution to the list of options.
            hole_options.append(tree_substitution)
        # Return reverse sketches that can fill the hole. 
        if (all(isinstance(x, ast.Constant) for x in hole_options)):
            sketches = []
            seen_sketches = set()
            for x in hole_options:
                x_str = ast.unparse(x)
                # If we haven't seen this value create a reverse sketch of it. 
                if x_str not in seen_sketches: 
                    seen_sketches.add(x_str)
                    sketches.append(ReverseSketch(x, [], [], []))
            return sketches
        return trees_uppper_bounds(hole_options)

    # A string of the reverse sketch. 
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
    return ReverseSketch(reverse_sketch, trees, holes, substitutions)

'''
Anti-unify n trees. 
@param list of candidate program ASTS.
@return the most specific generalization of n trees. 
'''
def trees_uppper_bounds(trees: list[ast.AST]):
    # Group trees by root node type. 
    grouped_dict = group_trees_by_type(trees)
    # Anti-unify each group. 
    return [antiunfy(group_items) for group, group_items in grouped_dict.items()]

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
    # Store the selected hole. 
    hole_id = int(input(f"Which hole would you like to expand 0-{len(selected_sketch.holes)-1}: "))
    # Expand the selected hole.
    interact(expand_hole(selected_sketch, hole_id))

if __name__ == "__main__":
    trees = read_trees("input-file.txt")
    reverse_sketches = trees_uppper_bounds(trees)
    interact(reverse_sketches)
    # First reverse sketch. 
    # test_sketch = reverse_sketches[0]
    # print(ast.unparse(test_sketch.sketch_AST))
    # # for hole_id in range(len(test_sketch.holes)):
    # test_sketches2 = expand_hole(test_sketch, 0)
    # expand_hole(test_sketches2[1], 0)
    
