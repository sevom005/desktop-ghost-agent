import turtle
import math
import random

# Setup screen
screen = turtle.Screen()
screen.setup(width=800, height=800)
screen.bgcolor("#0B0F19")
screen.title("Cybernetic Geometric Mandala")
screen.tracer(0)

# Create primary turtle
t = turtle.Turtle()
t.hideturtle()
t.speed(0)
t.width(1.5)

def draw_neon_circle(x, y, radius, color, width=2):
    t.penup()
    t.goto(x, y - radius)
    t.pendown()
    t.pencolor(color)
    t.width(width)
    t.circle(radius)

def draw_star_burst(x, y, size, num_rays, color):
    t.penup()
    t.goto(x, y)
    t.pendown()
    t.pencolor(color)
    for _ in range(num_rays):
        t.forward(size)
        t.backward(size)
        t.left(360 / num_rays)

def draw_complex_mandala():
    colors = ["#00FFFF", "#FF00FF", "#00FF66", "#FFCC00", "#9900FF"]
    
    # Outer geometric rings & glowing orbits
    for r in range(120, 360, 40):
        c = colors[(r // 40) % len(colors)]
        draw_neon_circle(0, 0, r, c, width=2)
    
    # Intricate rotating star petals
    petals = 36
    for i in range(petals):
        angle = i * (360 / petals)
        t.penup()
        t.goto(0, 0)
        t.setheading(angle)
        t.pendown()
        t.pencolor(colors[i % len(colors)])
        t.width(1)
        
        # Draw elegant curved petal geometry
        t.forward(220)
        t.left(45)
        t.forward(60)
        t.backward(60)
        t.right(90)
        t.forward(60)
        t.backward(60)
        t.left(45)
        t.backward(220)
        
    # Center holographic core
    draw_star_burst(0, 0, 100, 18, "#FFFFFF")
    draw_neon_circle(0, 0, 50, "#00FFFF", 3)
    draw_neon_circle(0, 0, 20, "#FF00FF", 4)
    
    # Outer decorative nodes
    for i in range(12):
        angle = i * 30
        rad = 360
        nx = rad * math.cos(math.radians(angle))
        ny = rad * math.sin(math.radians(angle))
        draw_neon_circle(nx, ny, 15, "#FFCC00", 2)

# Execute drawing
draw_complex_mandala()
screen.update()

# Keep window open
turtle.done()
