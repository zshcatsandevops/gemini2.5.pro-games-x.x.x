#!/usr/bin/env python3
# ============================================================
#  Ultra! Kirby pc port 2025 hdr
#  Platformer — self-contained Pygame build
#  No external assets: all art & sound generated on the fly
#  OST-free edition (no looping background music)
# ============================================================

import pygame, numpy as np, math, random, sys, asyncio, platform

pygame.init()
try:
    pygame.mixer.init(frequency=44100, size=-16, channels=1)
except Exception:
    pass  # run without sound if mixer fails (headless environments)

# ------------------------------------------------------------ 
# Window / timing
# ------------------------------------------------------------ 
W, H = 600, 400
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption("Ultra! Kirby pc port 2025 hdr")
clock = pygame.time.Clock()

# ------------------------------------------------------------ 
# Utility: make sine wave tones
# ------------------------------------------------------------ 
def tone(freq, ms, vol=0.4):
    sample_rate = 44100
    n = int(sample_rate * ms / 1000)
    t = np.arange(n)
    buf = (np.sin(2 * math.pi * freq * t / sample_rate) * 32767 * vol).astype(np.int16)
    try:
        return pygame.mixer.Sound(buffer=buf)
    except Exception:
        # Some pygame builds expect raw bytes
        return pygame.mixer.Sound(buffer=buf.tobytes())

boost_snd = tone(880, 140) if pygame.mixer.get_init() else None
zap_snd  = tone(520, 100) if pygame.mixer.get_init() else None

# ------------------------------------------------------------ 
# Game constants / colors
# ------------------------------------------------------------ 
FLOOR_Y = 330
SPACE   = (20, 30, 80)      # Dark starry background
ASTRO   = (100, 255, 150)   # Glowing green for ground
GLOW    = (200, 150, 255)   # Purple glow for player
STARBLUE= (50, 150, 255)    # Blue for boss accents
METEOR  = (150, 100, 50)    # Brownish for boss core
BLACK   = (0, 0, 0)
WHITE   = (255, 255, 255)

GALAXY_LEN = 2200  # side-scrolling galaxy length

font = pygame.font.SysFont("consolas", 18)

# ------------------------------------------------------------ 
# Input mapping with pressed/just-pressed helpers
# ------------------------------------------------------------ 
class Input:
    def __init__(self):
        self.prev = pygame.key.get_pressed()
        self.cur  = self.prev

        # Action -> list of keys (mirrored WASD + arrows + extra boost keys)
        self.binds = {
            "left":  [pygame.K_a, pygame.K_LEFT],
            "right": [pygame.K_d, pygame.K_RIGHT],
            "boost": [pygame.K_SPACE, pygame.K_z, pygame.K_k, pygame.K_w, pygame.K_UP],
            "pause": [pygame.K_p],
            "start": [pygame.K_RETURN],
        }

    def update(self):
        self.prev = self.cur
        self.cur = pygame.key.get_pressed()

    def _any(self, keys, state):
        return any(state[k] for k in keys)

    def down(self, action):
        return self._any(self.binds[action], self.cur)

    def just_pressed(self, action):
        # True if any mapped key transitioned from up->down
        return any(self.cur[k] and not self.prev[k] for k in self.binds[action])

inputs = Input()

# ------------------------------------------------------------ 
# Player with polished movement (coyote, buffer, variable boost)
# ------------------------------------------------------------ 
class StarSprite:
    def __init__(self):
        self.r = 18
        self.x, self.y = 100, FLOOR_Y
        self.vx, self.vy = 0.0, 0.0
        self.on_ground = True

        # Tunables
        self.max_speed = 180.0     # px/s
        self.accel     = 1200.0    # px/s^2 (when pressing a direction)
        self.friction  = 6.5       # proportional decay when no input
        self.gravity   = 1500.0    # base gravity
        self.boost_vel = -420.0    # base boost impulse
        self.fall_mult = 1.35      # extra gravity when falling
        self.low_mult  = 2.0       # extra gravity if boost released early

        # Boost quality-of-life
        self.coyote_max = 0.12     # seconds after stepping off edge
        self.buffer_max = 0.12     # seconds if boost pressed just before landing
        self.coyote_t   = 0.0
        self.buffer_t   = 0.0

    def rect(self):
        return pygame.Rect(int(self.x - self.r), int(self.y - self.r), self.r * 2, self.r * 2)

    def try_boost(self):
        self.vy = self.boost_vel
        self.on_ground = False
        self.coyote_t = 0.0
        self.buffer_t = 0.0
        if boost_snd: boost_snd.play()

    def update(self, dt):
        # Horizontal input -> acceleration/friction
        want_left  = inputs.down("left")
        want_right = inputs.down("right")
        move_dir = (-1 if want_left and not want_right else
                     1 if want_right and not want_left else 0)

        if move_dir != 0:
            self.vx += move_dir * self.accel * dt
        else:
            # Exponential-ish friction
            self.vx *= max(0.0, 1.0 - self.friction * dt)

        # Clamp speed
        if self.vx >  self.max_speed: self.vx =  self.max_speed
        if self.vx < -self.max_speed: self.vx = -self.max_speed

        # Boost buffering & coyote time
        if self.on_ground:
            self.coyote_t = self.coyote_max
        else:
            self.coyote_t -= dt

        if inputs.just_pressed("boost"):
            self.buffer_t = self.buffer_max
        else:
            self.buffer_t -= dt

        if self.buffer_t > 0 and self.coyote_t > 0:
            self.try_boost()

        # Gravity with fall/low multipliers
        g = self.gravity
        if self.vy > 0:          # falling
            g *= self.fall_mult
        elif self.vy < 0 and not inputs.down("boost"):  # rising but boost released early
            g *= self.low_mult
        self.vy += g * dt

        # Integrate
        self.x += self.vx * dt
        self.y += self.vy * dt

        # Ground collision
        if self.y >= FLOOR_Y:
            self.y = FLOOR_Y
            self.vy = 0.0
            self.on_ground = True
        else:
            self.on_ground = False

        # Galaxy bounds
        if self.x < 20: self.x, self.vx = 20, 0.0
        if self.x > GALAXY_LEN - 20: self.x, self.vx = GALAXY_LEN - 20, 0.0

    def draw(self, surf, camx):
        cx = int(self.x - camx)
        cy = int(self.y)
        pygame.draw.circle(surf, GLOW, (cx, cy), self.r)
        # Glow spots
        pygame.draw.circle(surf, WHITE, (cx - 5, cy - 4), 3)
        pygame.draw.circle(surf, BLACK, (cx - 5, cy - 4), 2)
        pygame.draw.circle(surf, WHITE, (cx + 5, cy - 4), 3)
        pygame.draw.circle(surf, BLACK, (cx + 5, cy - 4), 2)

# ------------------------------------------------------------ 
# Enemies (original): "NebulaDrifter"
# ------------------------------------------------------------ 
class NebulaDrifter:
    def __init__(self, x):
        self.x = float(x)
        self.y = float(FLOOR_Y)
        self.dir = random.choice([-1, 1])
        self.dead = False

    def rect(self):
        return pygame.Rect(int(self.x - 10), int(self.y - 10), 20, 20)

    def update(self, dt):
        if self.dead: return
        self.x += self.dir * 80.0 * dt
        if self.x < 80 or self.x > GALAXY_LEN - 80:
            self.dir *= -1

    def draw(self, surf, camx):
        if self.dead: return
        sx = int(self.x - camx)
        if -40 <= sx <= W + 40:
            pygame.draw.rect(surf, (255, 100, 150), (sx - 10, int(self.y) - 10, 20, 20))

# ------------------------------------------------------------ 
# Boss (original): "CosmoTitan"
# ------------------------------------------------------------ 
class CosmoTitan:
    def __init__(self, x):
        self.x, self.y = float(x), float(FLOOR_Y - 60)
        self.hp = 6
        self.timer = 0.0

    def rect(self):
        return pygame.Rect(int(self.x - 40), int(self.y - 80), 80, 140)

    def update(self, dt):
        self.timer += dt  # could be used for attacks later

    def draw(self, surf, camx):
        sx = int(self.x - camx)
        if -120 <= sx <= W + 120:
            # Core
            pygame.draw.rect(surf, METEOR, (sx - 15, int(self.y), 30, 80))
            # Energy field
            pygame.draw.circle(surf, STARBLUE, (sx, int(self.y) - 40), 50)
            # Features
            pygame.draw.circle(surf, BLACK, (sx - 15, int(self.y) - 40), 6)
            pygame.draw.circle(surf, BLACK, (sx + 15, int(self.y) - 40), 6)
            pygame.draw.rect(surf, BLACK, (sx - 10, int(self.y) - 15, 20, 10))

# ------------------------------------------------------------ 
# Background
# ------------------------------------------------------------ 
def draw_background(surf, camx):
    surf.fill(SPACE)
    # Parallax stars (looping)
    star_spacing = 140
    for i in range(-2, int(W / star_spacing) + 4):
        x = i * star_spacing - int(camx * 0.5) % star_spacing
        pygame.draw.circle(surf, WHITE, (x, 60), 10)
    pygame.draw.rect(surf, ASTRO, (0, FLOOR_Y, W, H - FLOOR_Y))

# ------------------------------------------------------------ 
# Game setup
# ------------------------------------------------------------ 
player = StarSprite()
drifters = [NebulaDrifter(x) for x in (350, 700, 1100, 1500, 1800)]
titan = CosmoTitan(GALAXY_LEN - 180)
score = 0
state = "menu"
paused = False
camera_x = 0.0

# ------------------------------------------------------------ 
# Main loop
# ------------------------------------------------------------ 
async def main():
    global state, paused, camera_x, score, player, drifters, titan
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                pygame.quit(); sys.exit()

        inputs.update()

        # Menu
        if state == "menu":
            screen.fill((10, 10, 50))
            title = font.render("Ultra! Kirby pc port 2025 hdr", True, (200, 180, 255))
            hint  = font.render("Press ENTER to start  (WASD/Arrows to move, Z/Space to boost)", True, WHITE)
            screen.blit(title, (W/2 - title.get_width()/2, 150))
            screen.blit(hint,  (W/2 - hint.get_width()/2, 200))
            if inputs.just_pressed("start"):
                state = "play"; score = 0
                player = StarSprite()
                drifters = [NebulaDrifter(x) for x in (350, 700, 1100, 1500, 1800)]
                titan = CosmoTitan(GALAXY_LEN - 180)
                camera_x = 0.0
            pygame.display.flip()
            clock.tick(60)
            await asyncio.sleep(1.0 / 60)
            continue

        # Gameplay
        if state == "play":
            # Toggle pause
            if inputs.just_pressed("pause"):
                paused = not paused

            dt = clock.tick(60) / 1000.0
            if paused:
                # Draw paused overlay
                draw_background(screen, camera_x)
                player.draw(screen, camera_x)
                for d in drifters: d.draw(screen, camera_x)
                titan.draw(screen, camera_x)
                overlay = font.render("Paused (P)", True, BLACK)
                screen.blit(overlay, (W//2 - overlay.get_width()//2, 60))
                pygame.display.flip()
                await asyncio.sleep(1.0 / 60)
                continue

            # Update player & galaxy
            player.update(dt)
            for d in drifters:
                d.update(dt)
                if not d.dead and d.rect().colliderect(player.rect()):
                    if zap_snd: zap_snd.play()
                    d.dead = True
                    score += 1

            # Titan logic when on screen
            titan.update(dt)
            if titan.rect().colliderect(player.rect()) and titan.hp > 0:
                titan.hp -= 1
                if zap_snd: zap_snd.play()
                if titan.hp <= 0:
                    state = "win"

            # Camera centers on player
            camera_x = max(0.0, min(GALAXY_LEN - W, player.x - W * 0.5))

            # Draw
            draw_background(screen, camera_x)
            player.draw(screen, camera_x)
            for d in drifters:
                if -40 <= (d.x - camera_x) <= W + 40:
                    d.draw(screen, camera_x)
            titan.draw(screen, camera_x)

            # HUD
            screen.blit(font.render(f"Score: {score}", True, BLACK), (10, 10))
            dist = int(max(0, titan.x - player.x))
            screen.blit(font.render(f"Sector 1 — Astral Fields   Boss in: {dist} px", True, BLACK), (10, 32))

            pygame.display.flip()

        elif state == "win":
            screen.fill((200, 220, 255))
            txt = font.render("You defeated the boss! Press ENTER for menu", True, BLACK)
            screen.blit(txt, (W/2 - txt.get_width()/2, H/2))
            if inputs.just_pressed("start"):
                state = "menu"
            pygame.display.flip()
            clock.tick(60)
        
        await asyncio.sleep(1.0 / 60)

if platform.system() == "Emscripten":
    asyncio.ensure_future(main())
else:
    if __name__ == "__main__":
        asyncio.run(main())
