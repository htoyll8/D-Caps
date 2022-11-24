import ast
from itertools import zip_longest, combinations, product, starmap
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

    def visit(self, node: ast.AST) -> Any:
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def visit_Module(self, node: ast.AST) -> Any:
        # Cannot remove modules.
        return super().generic_visit(node)
    
    def generic_visit(self, node: ast.AST) -> Any:
        hole = ast.Name(id=f'?', ctx="")
        if node.marked:
            # print("Retuning hole... ", type(node), ast.unparse(node), ast.unparse(hole))
            for k,v in self.del_dict.items(): 
                if (is_equal(k, node)):
                    l = v
                    l.append(k)
                    if all(isinstance(item, type(k)) for item in l):
                        common_type = extract_common_type(k)
                        hole = ast.Name(id=f'{common_type}?', ctx="")
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

def get_hole_idxs(holes_dict, idxs):
    new_holes_list = []
    holes_list = list(holes_dict)
    for idx in idxs:
        hole_key = holes_list[idx]
        new_holes_list.append(holes_dict[hole_key])
    return new_holes_list

def expand_hole_combos(expanded_holes):
    keys = []
    for x in expanded_holes:
        keys.append(list(x.keys()))
    combinations = list(product(keys))
    for c in combinations:
        print("Combo: ", c)

def expand_hole_util(to_expand_holes):
    expanded_holes = []
    for to_expand_hole in to_expand_holes:
        cur_level_expanded_holes = dict()
        cur_level_seen = []
        for c in combinations(to_expand_hole, 2):
            del_dict = compare_trees(c[0], c[1:], {})
            _, reverse_sketch, _ = generalize_tree(c[0], del_dict)
            if (reverse_sketch != ast.unparse(c[0]) and reverse_sketch != ast.unparse(c[1])):
                cur_level_seen.extend(list(map(lambda x: ast.unparse(x), c)))
            if (reverse_sketch not in cur_level_seen):
                cur_level_expanded_holes.setdefault(reverse_sketch, []).extend(c) 
        expanded_holes.append(cur_level_expanded_holes)
    expand_hole_combos(expanded_holes)
    return expanded_holes
    
def expand_hole(sketch_ast, holes_dict):
    to_expand = get_holes_from_user()
    print(f"Expanding {to_expand}: ", ast.unparse(sketch_ast))
    to_expand_holes = get_hole_idxs(holes_dict, to_expand)
    expand_hole_util(to_expand_holes)

def trees_uppper_bounds(trees):
    # Group trees.
    grouped_dict = group_trees_by_type(trees)
    # Generalize typed group. 
    reverse_sketches = []
    for _, group_items in grouped_dict.items():
        del_dict = compare_trees(group_items[0], group_items[1:], {})
        reverse_sketch_ast, reverse_sketch, _ = generalize_tree(group_items[0], del_dict)
        reverse_sketches.append(reverse_sketch)
        print(reverse_sketch)
        # if (del_dict):
        #     expand_hole(reverse_sketch_ast, del_dict)
        print("==================================")
    return grouped_dict, reverse_sketches

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
        ast.parse("str[1:3]"),
        ast.parse("str[1:len('a')]"),
        ast.parse("str[1:len('b')]"),
        ast.parse("str[2:1]"),
        ast.parse("str.split(sep)[1:3]"),
        ast.parse("str.split(sep)[1:2]"),
        ast.parse("str.split(sep)[0]"),
        ast.parse("str.split(sep)[1]"),
        ast.parse("str.split(sep)[2]"),
        ast.parse("str.split(sep)[lo[1]]"),
        ast.parse("str.split(sep)[lo[2]]"),
    ]
    trees = read_file("input-file.txt")
    groups, sketches = trees_uppper_bounds(trees)

    












































def insert_hole_sketch_util(reverse_sketch_ast, node_to_insert, hole_to_fill):
    TreeMarker().visit(reverse_sketch_ast)
    tree_nodes = TreeCollector().collect(reverse_sketch_ast)
    idx_to_mark = tree_nodes.index(hole_to_fill)
    tree_nodes[idx_to_mark].marked = True
    reverse_sketch_ast_copy = copy.deepcopy(reverse_sketch_ast)
    HoleInserter(node_to_insert).visit(reverse_sketch_ast_copy)
    return reverse_sketch_ast_copy

# Fills the hole and returns the new sketch. 
def insert_holes(reverse_sketch_ast, hole_sketches, hole_idx):
    hole_nodes = HoleCollector().collect(reverse_sketch_ast)
    hole_to_fill = hole_nodes[hole_idx]
    seen = []
    for hole_sketch in hole_sketches:
        # print("Inserting... ", ast.unparse(hole_sketch), f" into the {hole_idx} hole ", ast.unparse(reverse_sketch_ast))
        filled_sketch = insert_hole_sketch_util(reverse_sketch_ast, hole_sketch, hole_to_fill)
        filled_sketch_str = ast.unparse(filled_sketch)
        if (filled_sketch_str not in seen):
            # print("\t\t", filled_sketch_str)
            seen.append(filled_sketch)
    return seen

# Returns all of the things that can fill the hole along with its deletion dictionary.
def expand_holes_util(hole_options):
    grouped_dict = group_trees_by_type(hole_options)
    hole_sketches = []
    # Generalize typed group. 
    for _, group_items in grouped_dict.items():
        head, rest = group_items[0], group_items[1:]
        del_dict = compare_trees(head, rest, {})
        # Append all options if the group elements are constants. 
        if (isinstance(head, ast.Constant) and head in del_dict):
            hole_sketches.append((head, {}))
            for tree in rest: 
                hole_sketches.append((tree, {}))
        #  Append generalizations of subsets of the hole options. 
        else: 
            reverse_sketch_ast, _, _ = generalize_tree(head, del_dict)
            hole_sketches.append((reverse_sketch_ast, del_dict))
    return hole_sketches

def expand_hole2(reverse_sketch_ast, del_dict, seen_holes):
    hole_idx = int(input(f"Pick hole to expand: {0} - {len(del_dict)-1} for {ast.unparse(reverse_sketch_ast)}: "))
    seen_holes.append(hole_idx)
    hole_key = list(del_dict)[hole_idx]
    hole_options = del_dict[hole_key]
    # print("Hole options: ", hole_options)
    hole_options.insert(0, hole_key)
    hole_sketches_tup = expand_holes_util(hole_options)
    hole_sketches = list(map(lambda x: x[0], hole_sketches_tup))
    # print("Hole sketches: ", hole_sketches)
    filled_sketches = insert_holes(reverse_sketch_ast, hole_sketches, hole_idx)
    seen = []

    for idx, filled_sketch in enumerate(filled_sketches):
        filled_sketch_str = ast.unparse(filled_sketch)
        if (filled_sketch_str not in seen):
            print(f"\t\t {idx}: ", filled_sketch_str)
            seen.append(filled_sketch_str)
    sketch_idx = int(input(f"Pick a sketch to expand 0 - {len(filled_sketches)-1}: "))
    print("Sketch id: ", sketch_idx, hole_sketches_tup[sketch_idx])
    
    if hole_sketches_tup[sketch_idx][1]:
        new_hole = list(hole_sketches_tup[sketch_idx][1].items())[0]
        new_del_dict = OrderedDict([new_hole if k == hole_key else (k, v) for k, v in del_dict.items()])
        expand_hole2(filled_sketches[sketch_idx], new_del_dict, seen_holes)
    elif len(seen_holes) < len(del_dict):
        new_hole = list(hole_sketches_tup[sketch_idx][1].items())[0]
        new_del_dict = OrderedDict([new_hole if k == hole_key else (k, v) for k, v in del_dict.items()])
        expand_hole2(filled_sketches[sketch_idx], new_del_dict, seen_holes)
    else:
        final_sketch = filled_sketches[sketch_idx]
        print("Final sketch: ", ast.unparse(final_sketch))











# class HoleOption(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     option = db.Column(db.String(100))
#     hole_id = db.Column(db.Integer, db.ForeignKey('hole.id'))

# class Hole(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     sketch_id = db.Column(db.Integer, db.ForeignKey('sketch.id'))
#     hole_options = db.relationship('HoleOption', backref="hole")

# class SketchModel(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     val = db.Column(db.String(100), nullable=False)
#     holes = db.relationship('Hole', backref='sketch')

#     def __repr__(self) -> str:
#         return f"Sketch(val = {self.val}, holes={self.holes})"

# sketch_put_args = reqparse.RequestParser()
# sketch_put_args.add_argument("val", type=str, help="Value of the sketch is required", required=True)
# sketch_put_args.add_argument("holes", type=str, help="Holes of the sketch are required")

# resource_fields = {
#     'id': fields.Integer,
#     'val': fields.String,
#     'holes': fields.List(fields.Nested(Hole))
# }

# class VideoModel(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(100), nullable=False)
#     views = db.Column(db.Integer, nullable=False)
#     likes = db.Column(db.Integer, nullable=False)

#     def __repr__(self) -> str:
#         return f"Video(name = {name}, views = {views}, likes = {likes})"

# # Create database with above model. 
# # db.create_all()

# video_put_args = reqparse.RequestParser()
# video_put_args.add_argument("name", type=str, help="Name of the video is required", required=True)
# video_put_args.add_argument("views", type=int, help="Views of the video is required", required=True)
# video_put_args.add_argument("likes", type=int, help="Likes on the video is required", required=True)

# video_update_args = reqparse.RequestParser()
# video_update_args.add_argument("name", type=str, help="Name of the video is required")
# video_update_args.add_argument("views", type=int, help="Views of the video is required")
# video_update_args.add_argument("likes", type=int, help="Likes on the video is required")

# resource_fields = {
#     'id': fields.Integer,
#     'name': fields.String,
#     'views': fields.Integer, 
#     'likes': fields.Integer
# }

# class Video(Resource):
#     @marshal_with(resource_fields)
#     def get(self, video_id):
#         result = VideoModel.query.filter_by(id=video_id).first()
#         if not result:
#             abort(404, message="Could not find video with that id... ")
#         return result
    
#     @marshal_with(resource_fields)
#     def put(self, video_id):
#         args = video_put_args.parse_args()
#         result = VideoModel.query.filter_by(id=video_id).first()
#         if result:
#             abort(409, message="Video id exists...")
#         video = VideoModel(id=video_id, name=args['name'], views=args['views'], likes=args['likes'])
#         db.session.add(video)
#         db.session.commit()
#         return video, 201
    
#     @marshal_with(resource_fields)
#     def patch(self, video_id):
#         args = video_update_args.parse_args()
#         result = VideoModel.query.filter_by(id=video_id).first()
#         if not result: 
#             abort(404, message="Video doesn't exist, cannot update... ")
        
#         if args['name']: 
#             result.name = args['name']
#         if args['views']: 
#             result.views = args['views']
#         if args['likes']: 
#             result.likes = args['likes']
        
#         db.session.commit()

#         return result

#     def delete(self, video_id):
#         return '', 204

# api.add_resource(Video, "/video/<int:video_id>")

# if __name__ == "__main__":
#     app.run(debug=True)
    # trees = [
    #     ast.parse("str[1:3]"),
    #     ast.parse("str[1:len('a')]"),
    #     ast.parse("str[1:len('b')]"),
    #     ast.parse("str[2:1]"),
    #     ast.parse("str.split(sep)[1:3]"),
    #     ast.parse("str.split(sep)[1:2]"),
    #     ast.parse("str.split(sep)[0]"),
    #     ast.parse("str.split(sep)[1]"),
    #     ast.parse("str.split(sep)[2]"),
    #     ast.parse("str.split(sep)[lo[1]]"),
    #     ast.parse("str.split(sep)[lo[2]]")
    # ]

    # trees = read_file("input-file2.txt")
    # trees_uppper_bounds(trees)
    


       