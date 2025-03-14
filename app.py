from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from PIL import Image
import requests
import random

app = Flask(__name__)

# Cấu hình upload
UPLOAD_FOLDER = os.path.join('static', 'avatars')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Tạo thư mục nếu chưa có
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your_secret_key'

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    blocked = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    avatar = db.Column(db.String(200), default='default_avatar.jpg')

    def __init__(self, username, password):
        self.username = username
        self.password = generate_password_hash(password)

    @property
    def is_active(self):
        return not self.blocked

    @property
    def is_authenticated(self):
        return True

    def get_id(self):
        return self.id

    def reset_password(self, new_password):
        self.password = generate_password_hash(new_password)

class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    checked = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    notes = db.relationship('TodoNote', backref='todo', lazy=True, cascade="all, delete-orphan")
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)

    def __init__(self, name, user_id):
        self.name = name
        self.user_id = user_id
        self.status = 'pending'
        self.created_at = datetime.utcnow()

class TodoNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    todo_id = db.Column(db.Integer, db.ForeignKey('todo.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, todo_id, content):
        self.todo_id = todo_id
        self.content = content

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    color = db.Column(db.String(7), default='#3498db')
    todos = db.relationship('Todo', backref='category', lazy=True)

    def __init__(self, name, user_id, color='#3498db'):
        self.name = name
        self.user_id = user_id
        self.color = color

login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route("/")
@app.route("/home")
@login_required
def home():
    if current_user.blocked:
        flash("Tài khoản của bạn đã bị khóa.")
        return redirect(url_for("login"))
    
    categories = Category.query.filter_by(user_id=current_user.id).all()
    selected_category = request.args.get('category_id', type=int)
    
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    todos_query = Todo.query.filter_by(user_id=current_user.id)
    if selected_category:
        todos_query = todos_query.filter_by(category_id=selected_category)
    
    # Tính toán thống kê
    total_todos = Todo.query.filter_by(user_id=current_user.id).count()
    total_categories = len(categories)
    completed_todos = Todo.query.filter_by(user_id=current_user.id, checked=True).count()
    
    pagination = todos_query.paginate(page=page, per_page=per_page)
    
    return render_template(
        "index.html",
        items=pagination.items,
        pagination=pagination,
        categories=categories,
        selected_category=selected_category,
        stats={
            'total_todos': total_todos,
            'total_categories': total_categories,
            'completed_todos': completed_todos
        }
    )

@app.route("/add_todo", methods=["POST"])
@login_required
def add_todo():
    todo_name = request.form.get("todo_name")
    category_id = request.form.get("category_id")
    
    if todo_name:
        new_todo = Todo(name=todo_name, user_id=current_user.id)
        if category_id:
            new_todo.category_id = int(category_id)
        db.session.add(new_todo)
        db.session.commit()
        flash("Đã thêm công việc thành công!")
    return redirect(url_for("home"))

@app.route("/checked/<int:todo_id>", methods=["POST"])
@login_required
def checked_todo(todo_id):
    todo = Todo.query.get_or_404(todo_id)
    if todo and (todo.user_id == current_user.id or current_user.is_admin):
        todo.checked = not todo.checked
        if todo.checked:
            todo.status = 'completed'
            todo.finished_at = datetime.utcnow()
        else:
            todo.status = 'in_progress'
            todo.finished_at = None
        db.session.commit()
        flash("Đã cập nhật trạng thái công việc!")
    else:
        flash("Không tìm thấy công việc hoặc bạn không có quyền cập nhật!")
    return redirect(url_for("home"))

@app.route("/delete_tasks", methods=["POST"])
@login_required
def delete_tasks():
    task_ids = request.form.getlist("task_ids")
    if not task_ids:
        flash("Chưa chọn công việc để xóa!")
        return redirect(url_for("home"))
    
    try:
        for task_id in task_ids:
            task = Todo.query.get(int(task_id))
            if task and (task.user_id == current_user.id or current_user.is_admin):
                db.session.delete(task)
                flash(f"Đã xóa công việc: {task.name}")
            else:
                flash(f"Không tìm thấy công việc hoặc bạn không có quyền xóa!")
        
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash("Có lỗi xảy ra khi xóa công việc!")
        print(f"Error: {e}")
    
    return redirect(url_for("home"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        # Kiểm tra username
        if len(username) < 3:
            flash("Tên đăng nhập phải có ít nhất 3 ký tự!", "danger")
            return redirect(url_for("register"))

        if not username.isalnum():
            flash("Tên đăng nhập chỉ được chứa chữ cái và số!", "danger")
            return redirect(url_for("register"))

        # Kiểm tra mật khẩu
        if len(password) < 6:
            flash("Mật khẩu phải có ít nhất 6 ký tự!", "danger")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("Mật khẩu xác nhận không khớp!", "danger")
            return redirect(url_for("register"))

        # Kiểm tra username đã tồn tại
        if User.query.filter_by(username=username).first():
            flash("Tên đăng nhập đã tồn tại!", "danger")
            return redirect(url_for("register"))

        try:
            # Tạo user mới
            new_user = User(username=username, password=password)
            db.session.add(new_user)
            db.session.commit()
            flash("Đăng ký thành công! Vui lòng đăng nhập.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            db.session.rollback()
            flash("Có lỗi xảy ra khi đăng ký!", "danger")
            print(f"Error: {e}")
            return redirect(url_for("register"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            if user.blocked:
                flash("Your account is blocked.")
                return redirect(url_for("login"))
            login_user(user)
            if user.is_admin:
                return redirect(url_for("admin"))
            return redirect(url_for("home"))
        flash("Invalid username or password.")
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have logged out successfully.")
    return redirect(url_for("login"))

@app.route("/admin")
@login_required
def admin():
    if not current_user.is_admin:
        flash("Access denied.")
        return redirect(url_for("home"))
    
    # Lấy tất cả người dùng và công việc của họ
    users = User.query.all()
    todos = Todo.query.all()
    categories = Category.query.all()
    
    # Tạo dictionary để lưu công việc và danh mục của mỗi người dùng
    user_stats = {}
    for user in users:
        user_todos = Todo.query.filter_by(user_id=user.id).all()
        user_categories = Category.query.filter_by(user_id=user.id).all()
        completed_todos = len([todo for todo in user_todos if todo.checked])
        user_stats[user.id] = {
            'todos': user_todos,
            'total_todos': len(user_todos),
            'completed_todos': completed_todos,
            'categories': user_categories,
            'total_categories': len(user_categories)
        }
    
    return render_template(
        "admin.html", 
        users=users, 
        user_stats=user_stats,
        total_stats={
            'users': len(users),
            'todos': len(todos),
            'categories': len(categories)
        }
    )

@app.route("/block_user/<int:user_id>", methods=["POST"])
@login_required
def block_user(user_id):
    if not current_user.is_admin:
        flash("Access denied.")
        return redirect(url_for("home"))
    user = User.query.get(user_id)
    if user:
        user.blocked = True
        db.session.commit()
        flash(f"User {user.username} has been blocked.")
    else:
        flash("User not found.")
    return redirect(url_for("admin"))

@app.route("/reset_password/<int:user_id>", methods=["POST"])
@login_required
def reset_password(user_id):
    if not current_user.is_admin:
        flash("Access denied.")
        return redirect(url_for("home"))
    user = User.query.get(user_id)
    new_password = request.form["new_password"]
    if user:
        user.reset_password(new_password)
        db.session.commit()
        flash(f"Password for {user.username} has been reset.")
    else:
        flash("User not found.")
    return redirect(url_for("admin"))

@app.route("/unblock_user/<int:user_id>", methods=["POST"])
@login_required
def unblock_user(user_id):
    if not current_user.is_admin:
        flash("Access denied.")
        return redirect(url_for("home"))
    
    user = User.query.get(user_id)
    if user:
        user.blocked = False
        db.session.commit()
        flash(f"User {user.username} has been unblocked.")
    else:
        flash("User not found.")
    
    return redirect(url_for("admin"))

@app.route("/edit_todo/<int:todo_id>", methods=["GET", "POST"])
@login_required
def edit_todo(todo_id):
    todo = Todo.query.get_or_404(todo_id)
    
    if request.method == "POST":
        new_name = request.form["todo_name"]
        if new_name:
            todo.name = new_name
            db.session.commit()
            flash("Task updated successfully!")
            return redirect(url_for("home"))
        else:
            flash("Task name cannot be empty.")
    
    return render_template("edit_todo.html", todo=todo)

@app.route("/todo/<int:todo_id>/notes")
@login_required
def todo_notes(todo_id):
    todo = Todo.query.get_or_404(todo_id)
    # Kiểm tra quyền: người tạo công việc hoặc admin
    if todo.user_id != current_user.id and not current_user.is_admin:
        flash("Bạn không có quyền xem ghi chú của công việc này!")
        return redirect(url_for("home"))

    notes = TodoNote.query.filter_by(todo_id=todo_id).order_by(TodoNote.created_at.desc()).all()
    return render_template("todo_notes.html", todo=todo, notes=notes)

@app.route("/todo/<int:todo_id>/add_note", methods=["POST"])
@login_required
def add_note(todo_id):
    todo = Todo.query.get_or_404(todo_id)
    # Kiểm tra quyền: người tạo công việc hoặc admin
    if todo.user_id != current_user.id and not current_user.is_admin:
        flash("Bạn không có quyền thêm ghi chú cho công việc này!")
        return redirect(url_for("home"))

    content = request.form.get("content")
    if content:
        try:
            note = TodoNote(todo_id=todo_id, content=content)
            db.session.add(note)
            db.session.commit()
            flash("Đã thêm ghi chú thành công!")
        except Exception as e:
            db.session.rollback()
            flash("Có lỗi xảy ra khi thêm ghi chú!")
            print(f"Error: {e}")
    else:
        flash("Nội dung ghi chú không được để trống!")
    
    return redirect(url_for("todo_notes", todo_id=todo_id))

@app.route("/note/<int:note_id>/delete", methods=["POST"])
@login_required
def delete_note(note_id):
    note = TodoNote.query.get_or_404(note_id)
    todo = Todo.query.get(note.todo_id)
    
    # Kiểm tra quyền: người tạo công việc hoặc admin
    if todo.user_id != current_user.id and not current_user.is_admin:
        flash("Bạn không có quyền xóa ghi chú này!")
        return redirect(url_for("home"))
    
    try:
        db.session.delete(note)
        db.session.commit()
        flash("Đã xóa ghi chú thành công!")
    except Exception as e:
        db.session.rollback()
        flash("Có lỗi xảy ra khi xóa ghi chú!")
        print(f"Error: {e}")
    
    return redirect(url_for("todo_notes", todo_id=todo.id))

@app.route("/note/<int:note_id>/edit", methods=["POST"])
@login_required
def edit_note(note_id):
    note = TodoNote.query.get_or_404(note_id)
    todo = Todo.query.get(note.todo_id)
    
    if todo.user_id != current_user.id:
        flash("Bạn không có quyền chỉnh sửa ghi chú này!")
        return redirect(url_for("home"))
    
    content = request.form.get("content")
    if content:
        note.content = content
        db.session.commit()
        flash("Đã cập nhật ghi chú thành công!")
    else:
        flash("Nội dung ghi chú không được để trống!")
    
    return redirect(url_for("todo_notes", todo_id=note.todo_id))

@app.route("/admin/user/<int:user_id>")
@login_required
def user_details(user_id):
    if not current_user.is_admin:
        flash("Access denied.")
        return redirect(url_for("home"))
    
    user = User.query.get_or_404(user_id)
    todos = Todo.query.filter_by(user_id=user_id).all()
    
    # Tính toán thống kê
    total_todos = len(todos)
    completed_todos = len([todo for todo in todos if todo.checked])
    completion_rate = (completed_todos / total_todos * 100) if total_todos > 0 else 0
    
    return render_template(
        "user_details.html",
        user=user,
        todos=todos,
        stats={
            'total': total_todos,
            'completed': completed_todos,
            'completion_rate': completion_rate
        }
    )

@app.template_filter('nl2br')
def nl2br(value):
    if value:
        return value.replace('\n', '<br>')
    return value

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_random_avatar(username):
    """Tạo avatar ngẫu nhiên từ API"""
    try:
        # Các style có sẵn
        styles = ['adventurer', 'adventurer-neutral', 'avataaars', 'big-ears', 
                 'big-ears-neutral', 'big-smile', 'bottts', 'croodles', 'croodles-neutral']
        
        # Chọn ngẫu nhiên một style
        style = random.choice(styles)
        
        # Tạo URL API
        api_url = f"https://avatar-placeholder.iran.liara.run/public/{style}/{username}"
        
        # Tải ảnh từ API
        response = requests.get(api_url)
        if response.status_code == 200:
            # Tạo tên file
            filename = f"avatar_{username}_{style}.png"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            # Lưu file
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            return filename
    except Exception as e:
        print(f"Error generating avatar: {e}")
    
    return 'default_avatar.jpg'

@app.route('/upload_avatar', methods=['POST'])
@login_required
def upload_avatar():
    try:
        # Nếu người dùng upload file
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename != '':
                if allowed_file(file.filename):
                    # Xóa avatar cũ
                    if current_user.avatar != 'default_avatar.jpg':
                        old_avatar = os.path.join(app.config['UPLOAD_FOLDER'], current_user.avatar)
                        if os.path.exists(old_avatar):
                            os.remove(old_avatar)
                    
                    # Lưu file mới
                    filename = secure_filename(f"user_{current_user.id}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    current_user.avatar = filename
                    db.session.commit()
                    flash('Avatar đã được cập nhật!', 'success')
                else:
                    flash('Định dạng file không hợp lệ', 'error')
        else:
            # Tạo avatar ngẫu nhiên
            try:
                response = requests.get(f'https://avatar-placeholder.iran.liara.run/public/boy/{current_user.username}')
                if response.status_code == 200:
                    # Xóa avatar cũ
                    if current_user.avatar != 'default_avatar.jpg':
                        old_avatar = os.path.join(app.config['UPLOAD_FOLDER'], current_user.avatar)
                        if os.path.exists(old_avatar):
                            os.remove(old_avatar)
                    
                    # Lưu avatar mới
                    filename = f"random_avatar_{current_user.id}.png"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    with open(filepath, 'wb') as f:
                        f.write(response.content)
                    current_user.avatar = filename
                    db.session.commit()
                    flash('Avatar ngẫu nhiên đã được tạo!', 'success')
            except Exception as e:
                flash('Không thể tạo avatar ngẫu nhiên', 'error')
                print(e)
    except Exception as e:
        flash('Có lỗi xảy ra', 'error')
        print(e)
    
    return redirect(url_for('profile'))

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')

@app.route("/update_status/<int:todo_id>", methods=["POST"])
@login_required
def update_status(todo_id):
    todo = Todo.query.get_or_404(todo_id)
    if todo and (todo.user_id == current_user.id or current_user.is_admin):
        new_status = request.form.get('status')
        if new_status in ['pending', 'in_progress', 'completed']:
            todo.status = new_status
            if new_status == 'completed':
                todo.checked = True
                todo.finished_at = datetime.utcnow()
            else:
                todo.checked = False
                todo.finished_at = None
            db.session.commit()
            flash("Đã cập nhật trạng thái công việc!")
    return redirect(url_for("home"))

@app.route("/categories")
@login_required
def categories():
    categories = Category.query.filter_by(user_id=current_user.id).all()
    return render_template("categories.html", categories=categories)

@app.route("/add_category", methods=["POST"])
@login_required
def add_category():
    name = request.form.get("name")
    color = request.form.get("color", "#3498db")
    
    if name:
        category = Category(name=name, user_id=current_user.id, color=color)
        db.session.add(category)
        db.session.commit()
        flash("Đã thêm danh mục thành công!")
    return redirect(url_for("categories"))

@app.route("/delete_category/<int:id>", methods=["POST"])
@login_required
def delete_category(id):
    try:
        category = Category.query.get_or_404(id)
        if category.user_id != current_user.id:
            flash("Bạn không có quyền xóa danh mục này!")
            return redirect(url_for("categories"))
        
        # Cập nhật các todo thuộc category này về null
        Todo.query.filter_by(category_id=id).update({Todo.category_id: None})
        db.session.delete(category)
        db.session.commit()
        flash("Đã xóa danh mục thành công!")
    except Exception as e:
        db.session.rollback()
        flash(f"Có lỗi xảy ra khi xóa danh mục: {str(e)}")
        print(f"Error deleting category: {e}")
    return redirect(url_for("categories"))

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        # Tạo tài khoản admin
        admin_username = "ThuyKieu"
        admin_password = "120604"
        new_admin = User.query.filter_by(username=admin_username).first()
        if not new_admin:
            new_admin = User(username=admin_username, password=admin_password)
            new_admin.is_admin = True
            db.session.add(new_admin)
            db.session.commit()
            print("Admin account created successfully!")

        # Thêm dữ liệu giả lập cho 100 nhiệm vụ
        if Todo.query.count() == 0:  # Chỉ thêm nếu chưa có nhiệm vụ nào
            for i in range(1, 101):
                new_todo = Todo(name=f"Task {i}", user_id=new_admin.id)
                db.session.add(new_todo)
            db.session.commit()
            print("Sample tasks created successfully!")

    app.run(debug=True)