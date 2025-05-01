import sys
import random
import argparse
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QRect, pyqtProperty
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QRadialGradient


class BorderEffectWindow(QWidget):
    def __init__(self, transparency=1.0):
        super().__init__()
        
        # Print debug info
        print(f"Initializing BorderEffectWindow with transparency: {transparency}")
        
        # Store transparency level (0.0 to 1.0)
        self.transparency = max(0.1, min(1.0, transparency))
        # Background overlay transparency (0.0 to 0.5)
        self.bg_transparency = 0.30  # Start with slight background visibility
        
        # Initialize attributes early to avoid access issues during resize events
        self.flame_points = []  # Initialize flame_points early
        self.border_width = 8
        self.border_colors = [
            QColor(255, 69, 0),   # Red-Orange
            QColor(255, 140, 0),  # Dark Orange
            QColor(255, 165, 0),  # Orange
            QColor(255, 215, 0),  # Gold
            QColor(255, 255, 0),  # Yellow
        ]
        # Background color (dark with initial transparency)
        self.bg_color = QColor(20, 20, 25, int(255 * self.bg_transparency))
        
        self.current_color_index = 0
        self.glow_intensity = 0
        self.glow_direction = 1  # 1: increasing, -1: decreasing
        
        # Set window to be frameless and transparent
        print("Setting window flags...")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Optional: Make window pass through mouse events (we'll keep mouse events active)
        # Uncomment this line for click-through behavior
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        
        # Set window to full screen
        print("Setting window to fullscreen...")
        self.showFullScreen()
        
        # Set up animation timer
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update_animation)
        self.animation_timer.start(50)  # Update every 50ms
        
        # Set up secondary pulsation timer for glow effect
        self.glow_timer = QTimer(self)
        self.glow_timer.timeout.connect(self.update_glow)
        self.glow_timer.start(30)  # Update every 30ms
        
        # Generate initial flame points
        self.generate_flame_points()
        
        # Display transparency help message
        print("Transparanlık Kontrolleri:")
        print("• Artırmak için + veya = tuşları")
        print("• Azaltmak için - veya _ tuşları")
        print("• Arkaplan şeffaflığı artırmak için [ tuşu")
        print("• Arkaplan şeffaflığı azaltmak için ] tuşu")
        print("• Çıkış için ESC tuşu")
    
    def generate_flame_points(self):
        """Generate random flame points around the border"""
        self.flame_points.clear()
        for i in range(100):
            side = random.randint(0, 3)  # 0: top, 1: right, 2: bottom, 3: left
            if side == 0:  # Top
                x = random.randint(0, self.width())
                y = random.randint(0, self.border_width)
            elif side == 1:  # Right
                x = random.randint(self.width() - self.border_width, self.width())
                y = random.randint(0, self.height())
            elif side == 2:  # Bottom
                x = random.randint(0, self.width())
                y = random.randint(self.height() - self.border_width, self.height())
            else:  # Left
                x = random.randint(0, self.border_width)
                y = random.randint(0, self.height())
            
            intensity = random.uniform(0.3, 1.0)
            direction = random.choice([1, -1])
            speed = random.uniform(0.02, 0.1)
            self.flame_points.append({
                'x': x, 'y': y, 'intensity': intensity,
                'direction': direction, 'speed': speed,
                'base_color': random.randint(0, len(self.border_colors) - 1)
            })
    
    def update_animation(self):
        # Slowly transition base color
        self.current_color_index = (self.current_color_index + 0.05) % len(self.border_colors)
        
        # Update flame points
        for point in self.flame_points:
            # Update intensity
            point['intensity'] += point['direction'] * point['speed']
            if point['intensity'] >= 1.0:
                point['intensity'] = 1.0
                point['direction'] = -1
            elif point['intensity'] <= 0.3:
                point['intensity'] = 0.3
                point['direction'] = 1
                # Occasionally change the base color
                if random.random() < 0.1:
                    point['base_color'] = random.randint(0, len(self.border_colors) - 1)
        
        # Update painting
        self.update()
    
    def update_glow(self):
        # Update global glow intensity
        self.glow_intensity += 0.05 * self.glow_direction
        if self.glow_intensity >= 1.0:
            self.glow_intensity = 1.0
            self.glow_direction = -1
        elif self.glow_intensity <= 0.4:
            self.glow_intensity = 0.4
            self.glow_direction = 1
    
    def resizeEvent(self, event):
        """Handle window resize by regenerating flame points"""
        # Make sure flame_points attribute exists before trying to clear it
        if hasattr(self, 'flame_points'):
            # Regenerate flame points for new window size
            self.generate_flame_points()
        else:
            # Create flame_points if it doesn't exist yet
            self.flame_points = []
            self.generate_flame_points()
            
        super().resizeEvent(event)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # First, paint the semi-transparent background for the center area
        painter.fillRect(self.rect(), self.bg_color)
        
        # Get two nearby colors for interpolation
        color_idx = int(self.current_color_index)
        next_idx = (color_idx + 1) % len(self.border_colors)
        fraction = self.current_color_index - color_idx
        
        # Interpolate between the two colors
        base_color = self.interpolate_colors(
            self.border_colors[color_idx], 
            self.border_colors[next_idx], 
            fraction
        )
        
        # Draw border rectangle with glow
        outer_rect = self.rect()
        inner_rect = outer_rect.adjusted(self.border_width, self.border_width, 
                                        -self.border_width, -self.border_width)
        
        # Create glow effect with transparency applied
        for i in range(self.border_width, 0, -1):
            # Apply global glow intensity and transparency
            color_intensity = (self.border_width - i) / self.border_width * self.glow_intensity * 0.8 + 0.2
            alpha = int(min(255, 255 * color_intensity * self.transparency))
            
            # Fix: Cast float values to integers for QColor with adjusted alpha for transparency
            border_color = QColor(
                int(min(255, base_color.red() * color_intensity)),
                int(min(255, base_color.green() * color_intensity)),
                int(min(255, base_color.blue() * color_intensity)),
                alpha
            )
            
            painter.setPen(QPen(border_color, 1))
            painter.drawRect(outer_rect.adjusted(i, i, -i, -i))
        
        # Draw flame points for additional effect with transparency
        for point in self.flame_points:
            color_idx = point['base_color']
            next_idx = (color_idx + 1) % len(self.border_colors)
            
            # Get flame color based on intensity
            flame_color = self.interpolate_colors(
                self.border_colors[color_idx],
                self.border_colors[next_idx],
                point['intensity']
            )
            
            # Apply transparency to flame color
            flame_color.setAlpha(int(255 * self.transparency))
            
            # Create radial gradient for each flame point
            gradient = QRadialGradient(point['x'], point['y'], 
                                      self.border_width * point['intensity'])
            gradient.setColorAt(0, flame_color)
            
            # Make a copy of the flame color with alpha=0
            transparent_flame = QColor(flame_color)
            transparent_flame.setAlpha(0)
            gradient.setColorAt(1, transparent_flame)
            
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(gradient))
            size = int(self.border_width * point['intensity'] * 2)
            painter.drawEllipse(QPoint(point['x'], point['y']), size, size)
    
    def interpolate_colors(self, color1, color2, fraction):
        # Linearly interpolate between two colors
        r = color1.red() * (1 - fraction) + color2.red() * fraction
        g = color1.green() * (1 - fraction) + color2.green() * fraction
        b = color1.blue() * (1 - fraction) + color2.blue() * fraction
        # Fix: Cast interpolated values to integers
        return QColor(int(r), int(g), int(b), 255)
    
    def adjust_transparency(self, delta):
        """Adjust transparency level"""
        self.transparency = max(0.1, min(1.0, self.transparency + delta))
        print(f"Kenar Transparanlığı: {self.transparency:.2f}")
    
    def adjust_bg_transparency(self, delta):
        """Adjust background transparency level"""
        # Limit background transparency between 0.0 (completely transparent) and 0.5 (semi-visible)
        self.bg_transparency = max(0.0, min(0.5, self.bg_transparency + delta))
        # Update the background color with new transparency
        self.bg_color.setAlpha(int(255 * self.bg_transparency))
        print(f"Arkaplan Transparanlığı: {self.bg_transparency:.2f}")
    
    def keyPressEvent(self, event):
        # Handle keyboard events
        key = event.key()
        
        if key == Qt.Key_Escape:
            # Exit on Escape key
            self.close()
        elif key == Qt.Key_Plus or key == Qt.Key_Equal:
            # Increase border transparency with + or = keys
            self.adjust_transparency(0.1)
        elif key == Qt.Key_Minus or key == Qt.Key_Underscore:
            # Decrease border transparency with - or _ keys
            self.adjust_transparency(-0.1)
        elif key == Qt.Key_BracketLeft:
            # Decrease background transparency with [ key (make more transparent)
            self.adjust_bg_transparency(-0.05)
        elif key == Qt.Key_BracketRight:
            # Increase background transparency with ] key (make more visible)
            self.adjust_bg_transparency(0.05)
    
    def close(self):
        """Close the window properly"""
        super().close()
        # No need to exit the app, just close this window


if __name__ == "__main__":
    # Only run this block when script is executed directly
    # Parse command line arguments for initial transparency
    parser = argparse.ArgumentParser(description='Animasyonlu kenarlık efekti penceresi')
    parser.add_argument('-t', '--transparency', type=float, default=0.8,
                        help='Başlangıç saydamlık değeri (0.1-1.0 arasında, varsayılan: 0.8)')
    
    args = parser.parse_args()
    print(f"Starting BorderEffectWindow application with transparency: {args.transparency}")
    
    app = QApplication(sys.argv)
    window = BorderEffectWindow(transparency=args.transparency)
    window.show()
    print("Border effect window shown, starting event loop")
    sys.exit(app.exec_())
else:
    print("border_effect.py module imported (not running directly)")
