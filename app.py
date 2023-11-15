from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate
from datetime import datetime, time, timedelta



app = Flask(__name__)

# 配置数据库
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lab.db'
app.config['SECRET_KEY'] = 'your-secret-key'  # 用于保护会话

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    password_hash = db.Column(db.String(100))
    role = db.Column(db.String(10))  # 'teacher' 或 'student'

class Equipment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    model = db.Column(db.String(80))
    status = db.Column(db.String(20), default='available')  # available, unavailable
    location = db.Column(db.String(120))


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    equipment_id = db.Column(db.Integer, db.ForeignKey('equipment.id'))
    date = db.Column(db.Date)
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)

    equipment = db.relationship('Equipment')
    user = db.relationship('User')


@app.route('/')
def home():
    return render_template('home.html')



@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        hashed_password = generate_password_hash(password)
        role = request.form.get('role')
        new_user = User(username=username, password_hash=hashed_password, role=role)
        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('home'))

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))


# 在初始化数据库之后
migrate = Migrate(app, db)

@app.route('/manage-equipment')
@login_required
def manage_equipment():
    if not is_teacher(current_user):
        return "访问被拒绝：权限不足", 403  # 或重定向到无权限页面
    equipments = Equipment.query.all()
    return render_template('manage_equipment.html', equipments=equipments)



#辅助函数来检查用户是否是老师
def is_teacher(user):
    return user.is_authenticated and user.role == 'teacher'


@app.route('/add-equipment', methods=['GET', 'POST'])
@login_required
def add_equipment():
    if not is_teacher(current_user):
        return "访问被拒绝：权限不足", 403  # 或重定向到无权限页面
    if request.method == 'POST':
        name = request.form.get('name')
        model = request.form.get('model')
        status = request.form.get('status')
        location = request.form.get('location')

        new_equipment = Equipment(name=name, model=model, status=status, location=location)
        db.session.add(new_equipment)
        db.session.commit()

        return redirect(url_for('manage_equipment'))

    return render_template('add_equipment.html')


@app.route('/edit-equipment/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_equipment(id):
    equipment = Equipment.query.get_or_404(id)

    if request.method == 'POST':
        equipment.name = request.form.get('name')
        equipment.model = request.form.get('model')
        equipment.status = request.form.get('status')
        equipment.location = request.form.get('location')

        db.session.commit()
        return redirect(url_for('manage_equipment'))

    return render_template('edit_equipment.html', equipment=equipment)


@app.route('/delete-equipment/<int:id>', methods=['POST'])
@login_required
def delete_equipment(id):
    equipment = Equipment.query.get_or_404(id)
    db.session.delete(equipment)
    db.session.commit()
    return redirect(url_for('manage_equipment'))



# book_equipment 路由允许用户提交预约，并将这些信息保存到数据库中
@app.route('/book-equipment', methods=['GET', 'POST'])
@login_required
def book_equipment():
    if request.method == 'POST':
        equipment_id = request.form.get('equipment')
        date_str = request.form.get('date')
        time_slot = request.form.get('time_slot')

        # 解析时间段
        start_hour, end_hour = map(int, time_slot.split('-'))
        start_time = time(start_hour, 0)  # 将小时转换为 time 对象
        end_time = time(end_hour, 0)

        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()

        # 检查冲突
        conflicting_bookings = Booking.query.filter(
            Booking.equipment_id == equipment_id,
            Booking.date == date_obj,
            Booking.end_time > start_time,
            Booking.start_time < end_time
        ).all()

        if conflicting_bookings:
            return "选定时间段已被预约。请选择其他时间。"  # 或者使用其他方式通知用户

        # 创建新预约
        new_booking = Booking(user_id=current_user.id, equipment_id=equipment_id,
                              date=date_obj, start_time=start_time, end_time=end_time)
        db.session.add(new_booking)
        db.session.commit()

        return redirect(url_for('view_bookings'))

    equipments = Equipment.query.all()  # 获取所有设备
    return render_template('book_equipment.html', equipments=equipments)


# view_bookings 路由则展示了当前用户的所有预约
@app.route('/view-bookings')
@login_required
def view_bookings():
    bookings = Booking.query.filter_by(user_id=current_user.id).all()
    return render_template('view_bookings.html', bookings=bookings)


# 取消预约
@app.route('/cancel-booking/<int:id>', methods=['POST'])
@login_required
def cancel_booking(id):
    booking = Booking.query.get_or_404(id)

    # 确保用户只能取消自己的预约
    if booking.user_id != current_user.id:
        return redirect(url_for('view_bookings'))  # 或者返回一个错误消息

    db.session.delete(booking)
    db.session.commit()
    return redirect(url_for('view_bookings'))


# 添加管理员角色
@app.route('/admin/bookings')
@login_required
def admin_bookings():
    if not current_user.is_admin:
        return redirect(url_for('home'))  # 或返回错误消息

    bookings = Booking.query.all()
    return render_template('admin_bookings.html', bookings=bookings)


@app.route('/edit-booking/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_booking(id):
    booking = Booking.query.get_or_404(id)

    # 确保用户只能编辑自己的预约
    if booking.user_id != current_user.id:
        return redirect(url_for('view_bookings'))  # 或者返回一个错误消息

    if request.method == 'POST':
        equipment_id = request.form.get('equipment')
        date = request.form.get('date')
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')

        # 检查冲突
        conflict_bookings = Booking.query.filter(
            Booking.id != id,
            Booking.equipment_id == equipment_id,
            Booking.date == date,
            Booking.start_time < end_time,
            Booking.end_time > start_time
        ).all()

        if conflict_bookings:
            # 处理冲突情况，例如返回错误消息
            return render_template('edit_booking.html', booking=booking, error='选定时间内设备已被预约。')

        # 更新预约信息
        booking.equipment_id = equipment_id
        booking.date = date
        booking.start_time = start_time
        booking.end_time = end_time
        db.session.commit()

        return redirect(url_for('view_bookings'))

    return render_template('edit_booking.html', booking=booking)

# 查看设备预约状态
@app.route('/equipment-schedule')
@login_required
def equipment_schedule():
    today = datetime.now().date()
    end_date = today + timedelta(days=7)
    schedule = {}

    equipments = Equipment.query.all()
    for equipment in equipments:
        bookings = Booking.query.filter(
            Booking.equipment_id == equipment.id,
            Booking.date >= today,
            Booking.date <= end_date
        ).join(User).add_columns(User.username, Booking.date, Booking.start_time, Booking.end_time).order_by(
            Booking.date, Booking.start_time).all()
        schedule[equipment.name] = bookings

    return render_template('equipment_schedule.html', schedule=schedule, today=today)