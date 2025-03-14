from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    blocked = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)

class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    checked = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    def __init__(self, name, user_id):
        self.name = name
        self.user_id = user_id
    @property
    def is_active(self):
        return not self.blocked  # Người dùng chỉ hoạt động nếu không bị khóa
    
    # Phương thức get_id
    def get_id(self):
        return self.id  # Trả về id của người dùng
    
    @property
    def is_authenticated(self):
        return True  # Người dùng đã đăng nhập
    def reset_password(self, new_password):
        self.password = generate_password_hash(new_password)