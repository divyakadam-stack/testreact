import os
import random
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pygame


SCREEN_WIDTH = 1400
SCREEN_HEIGHT = 900
FPS = 60

GRID_SIZE = 6
CELL_SIZE = 82
GRID_TOP = 190
HUMAN_GRID_LEFT = 86
AI_GRID_LEFT = 822
GRID_PIXELS = GRID_SIZE * CELL_SIZE

ROAD_LEFT = HUMAN_GRID_LEFT + GRID_PIXELS + 58
ROAD_WIDTH = 186
PLATTER_TOP = 730
PLATTER_HEIGHT = 132
MAX_TURNS = 10
STARTING_COINS = 50

ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
SOUND_DIR = os.path.join(ASSET_DIR, "sounds")

BUILD_PROPS = ("house", "park", "shop", "street")
SHUFFLED_BUILD_PROPS = ("house", "park", "shop", "street")
DESTROY_BONUS_CHANCE = 0.20
PROP_DIMS = {
    "park": (3, 3),
    "house": (2, 2),
    "shop": (1, 1),
    "street": (1, 1),
}
PROP_LABELS = {
    "house": "House",
    "park": "Park",
    "shop": "Shop",
    "street": "Street",
    "undo": "Undo",
    "destroy": "Destroy",
}
PROP_COINS = {
    "house": 3,
    "park": 3,
    "shop": 0,
    "street": 0,
    "undo": -2,
    "destroy": 0,
}

AI_SCRIPT = {
    1: "build",
    2: "build",
    3: "undo",
    4: "build",
    9: "destroy",
    10: "build",
}

COLORS = {
    "grass": (125, 176, 111),
    "grass_dark": (88, 137, 80),
    "panel": (255, 246, 223),
    "panel_shadow": (94, 74, 66),
    "grid": (218, 211, 184),
    "grid_alt": (204, 220, 176),
    "grid_line": (113, 132, 100),
    "road": (58, 61, 67),
    "road_edge": (93, 79, 72),
    "road_line": (238, 229, 198),
    "road_center": (224, 176, 48),
    "white": (255, 255, 255),
    "text": (38, 39, 49),
    "muted": (88, 91, 102),
    "coin": (250, 198, 49),
    "coin_dark": (191, 134, 25),
    "human": (86, 150, 196),
    "ai": (117, 159, 209),
    "green": (91, 176, 91),
    "red": (211, 78, 67),
    "orange": (227, 142, 57),
    "slot": (245, 232, 207),
    "slot_border": (109, 82, 70),
    "valid": (92, 210, 120),
    "invalid": (230, 72, 66),
}


@dataclass
class PlacedProp:
    id: int
    prop: str
    owner: str
    row: int
    col: int
    width: int
    height: int


@dataclass
class MoveRecord:
    action: str
    owner: str
    pos: Optional[tuple[int, int]]
    prop: Optional[str]
    target_owner: Optional[str] = None
    restored_item: Optional[PlacedProp] = None
    target_penalty: int = 0
    coin_delta: int = 0


@dataclass
class FloatingText:
    text: str
    pos: pygame.Vector2
    color: tuple[int, int, int]
    lifetime: float = 1.0

    def update(self, dt: float) -> bool:
        self.lifetime -= dt
        self.pos.y -= 38 * dt
        return self.lifetime > 0

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        alpha = max(0, min(255, int(255 * self.lifetime)))
        rendered = font.render(self.text, True, self.color)
        rendered.set_alpha(alpha)
        rect = rendered.get_rect(center=(int(self.pos.x), int(self.pos.y)))
        surface.blit(rendered, rect)


@dataclass
class AIAnimation:
    action: dict
    prop: str
    slot: int
    start: pygame.Vector2
    end: pygame.Vector2
    elapsed: float = 0.0
    duration: float = 0.75


class PropCard:
    def __init__(self, prop: str, slot_index: int, game: "BlockWarsGame"):
        self.prop = prop
        self.slot_index = slot_index
        self.game = game
        self.rect = pygame.Rect(0, 0, 104, 104)
        self.home = pygame.Vector2(0, 0)
        self.dragging = False
        self.drag_offset = pygame.Vector2()
        self.set_slot(slot_index)

    def set_slot(self, slot_index: int) -> None:
        self.slot_index = slot_index
        x = 420 + slot_index * 140
        y = PLATTER_TOP + 16
        self.home.update(x, y)
        self.rect.topleft = (x, y)

    def start_drag(self, mouse_pos: tuple[int, int]) -> bool:
        if self.rect.collidepoint(mouse_pos):
            self.dragging = True
            self.drag_offset = pygame.Vector2(self.rect.topleft) - pygame.Vector2(mouse_pos)
            return True
        return False

    def update_drag(self, mouse_pos: tuple[int, int]) -> None:
        if self.dragging:
            new_pos = pygame.Vector2(mouse_pos) + self.drag_offset
            self.rect.topleft = (int(new_pos.x), int(new_pos.y))

    def reset(self) -> None:
        self.dragging = False
        self.rect.topleft = (int(self.home.x), int(self.home.y))

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.rect(surface, COLORS["panel_shadow"], self.rect.move(5, 6), border_radius=18)
        pygame.draw.rect(surface, COLORS["slot"], self.rect, border_radius=18)
        pygame.draw.rect(surface, COLORS["slot_border"], self.rect, width=3, border_radius=18)

        image = self.game.assets.get(self.prop)
        if image:
            image = self.game.fit_image(image, (72, 66))
            image_rect = image.get_rect(center=(self.rect.centerx, self.rect.centery - 8))
            surface.blit(image, image_rect)
        else:
            pygame.draw.circle(surface, COLORS["coin"], self.rect.center, 28)

        label = self.game.font_small.render(PROP_LABELS[self.prop], True, COLORS["text"])
        surface.blit(label, label.get_rect(center=(self.rect.centerx, self.rect.bottom - 15)))

        coin_value = PROP_COINS[self.prop]
        if self.prop == "destroy":
            score_text = "0 / target -5"
        elif coin_value > 0:
            score_text = f"+{coin_value}"
        else:
            score_text = str(coin_value)
        score = self.game.font_tiny.render(score_text, True, COLORS["muted"])
        surface.blit(score, score.get_rect(center=(self.rect.centerx, self.rect.top + 13)))


class BlockWarsGame:
    def __init__(self) -> None:
        pygame.init()
        self.audio_enabled = self.init_audio()
        pygame.display.set_caption("BlockWars - Human vs AI")
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.clock = pygame.time.Clock()
        self.font_title = pygame.font.SysFont("arialrounded", 54, bold=True)
        self.font_big = pygame.font.SysFont("arialrounded", 38, bold=True)
        self.font_medium = pygame.font.SysFont("arialrounded", 28, bold=True)
        self.font_small = pygame.font.SysFont("arialrounded", 21, bold=True)
        self.font_tiny = pygame.font.SysFont("arialrounded", 16, bold=True)
        self.assets = self.load_assets()
        self.sounds = self.load_sounds()
        self.running = True
        self.reset_game()
        self.start_background_music()

    def init_audio(self) -> bool:
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            return True
        except pygame.error:
            return False

    def load_assets(self) -> dict[str, pygame.Surface]:
        files = {
            "house": "house.jpeg",
            "park": "park.jpeg",
            "shop": "shop.png",
            "street": "street.jpeg",
            "undo": "undo.jpeg",
            "destroy": "destroy.jpeg",
        }
        assets: dict[str, pygame.Surface] = {}
        for prop, filename in files.items():
            path = os.path.join(ASSET_DIR, filename)
            if not os.path.exists(path):
                continue
            try:
                assets[prop] = pygame.image.load(path).convert_alpha()
            except pygame.error:
                pass
        return assets

    def load_sounds(self) -> dict[str, pygame.mixer.Sound]:
        if not self.audio_enabled:
            return {}
        files = {
            "click": "mouse_click.mpeg",
            "pop": "pop.mpeg",
            "destroy": "destroy.mpeg",
            "victory": "victory.mpeg",
            "coins": "coins.mpeg",
            "lost": "lost.mpeg",
        }
        sounds = {}
        for name, filename in files.items():
            path = os.path.join(SOUND_DIR, filename)
            if not os.path.exists(path):
                continue
            try:
                sounds[name] = pygame.mixer.Sound(path)
            except pygame.error:
                pass
        return sounds

    def start_background_music(self) -> None:
        if not self.audio_enabled:
            return
        path = os.path.join(SOUND_DIR, "background_music.mpeg")
        if not os.path.exists(path):
            return
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(0.35)
            pygame.mixer.music.play(-1)
        except pygame.error:
            pass

    def play_sound(self, name: str) -> None:
        sound = self.sounds.get(name)
        if sound:
            sound.play()

    def play_drop_sounds(self, prop: str) -> None:
        if prop == "destroy":
            self.play_sound("destroy")
            return
        self.play_sound("pop")
        if PROP_COINS.get(prop, 0) > 0:
            self.play_sound("coins")

    @staticmethod
    def fit_image(image: pygame.Surface, bounds: tuple[int, int]) -> pygame.Surface:
        max_w, max_h = bounds
        width, height = image.get_size()
        scale = min(max_w / width, max_h / height)
        size = (max(1, int(width * scale)), max(1, int(height * scale)))
        return pygame.transform.smoothscale(image, size)

    def reset_game(self) -> None:
        self.human_grid: list[list[Optional[PlacedProp]]] = [[None for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        self.ai_grid: list[list[Optional[PlacedProp]]] = [[None for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        self.next_prop_id = 1
        self.scores = {"human": STARTING_COINS, "ai": STARTING_COINS}
        self.turns = {"human": 0, "ai": 0}
        self.histories: dict[str, list[MoveRecord]] = {"human": [], "ai": []}
        self.current_player = "human"
        self.started = False
        self.level_select = False
        self.difficulty = "hard"
        self.destroy_limits = {"human": 2, "ai": 3}
        self.destroy_given = {"human": 0, "ai": 0}
        self.destroy_rolls = {"human": 0, "ai": 0}
        self.destroy_roll_budget = 3 + MAX_TURNS
        self.game_over = False
        self.message = "Drag props from your platter onto the grid."
        self.dragged_card: Optional[PropCard] = None
        self.hover_target: Optional[tuple[str, int, int]] = None
        self.floating_texts: list[FloatingText] = []
        self.ai_pending = False
        self.ai_timer = 0.0
        self.ai_animation: Optional[AIAnimation] = None
        self.winner_text = ""
        self.human_platter = [PropCard(self.generate_platter_prop("human", i), i, self) for i in range(4)]
        self.ai_platter = [self.generate_platter_prop("ai", i) for i in range(4)]

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self.handle_events()
            self.update(dt)
            self.draw()
        pygame.quit()
        sys.exit()

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_r:
                    self.reset_game()
                    self.level_select = True
                elif event.key in (pygame.K_F12, pygame.K_s):
                    self.save_screenshot()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.handle_mouse_down(event.pos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.handle_mouse_up(event.pos)
            elif event.type == pygame.MOUSEMOTION:
                self.handle_mouse_motion(event.pos)

    def handle_mouse_down(self, pos: tuple[int, int]) -> None:
        if not self.started and not self.level_select:
            if self.play_button_rect().collidepoint(pos):
                self.level_select = True
            return

        if self.level_select:
            if self.easy_button_rect().collidepoint(pos):
                self.start_match("easy")
            elif self.hard_button_rect().collidepoint(pos):
                self.start_match("hard")
            return

        if self.game_over:
            if self.restart_button_rect().collidepoint(pos):
                self.reset_game()
                self.level_select = True
            return

        if self.current_player != "human" or self.ai_pending or self.ai_animation:
            return

        for card in reversed(self.human_platter):
            if card.start_drag(pos):
                self.play_sound("click")
                self.dragged_card = card
                return

    def handle_mouse_motion(self, pos: tuple[int, int]) -> None:
        self.hover_target = self.grid_from_mouse(pos)
        if self.dragged_card:
            self.dragged_card.update_drag(pos)

    def handle_mouse_up(self, pos: tuple[int, int]) -> None:
        if not self.dragged_card:
            return

        card = self.dragged_card
        target = self.grid_from_mouse(pos)
        if target and self.apply_human_prop(card.prop, target):
            self.play_drop_sounds(card.prop)
            self.replace_human_slot(card.slot_index)
            self.finish_turn("human")
        else:
            card.reset()
            self.message = "Invalid drop. Try a valid square on the correct side."
        self.dragged_card = None

    def update(self, dt: float) -> None:
        self.floating_texts = [text for text in self.floating_texts if text.update(dt)]
        if self.ai_animation:
            self.update_ai_animation(dt)
        if self.started and not self.game_over and self.ai_pending:
            self.ai_timer -= dt
            if self.ai_timer <= 0:
                self.ai_pending = False
                self.perform_ai_turn()

    def play_button_rect(self) -> pygame.Rect:
        return pygame.Rect(SCREEN_WIDTH // 2 - 130, 520, 260, 72)

    def easy_button_rect(self) -> pygame.Rect:
        return pygame.Rect(SCREEN_WIDTH // 2 - 315, 500, 270, 88)

    def hard_button_rect(self) -> pygame.Rect:
        return pygame.Rect(SCREEN_WIDTH // 2 + 45, 500, 270, 88)

    def restart_button_rect(self) -> pygame.Rect:
        return pygame.Rect(SCREEN_WIDTH // 2 - 120, 575, 240, 64)

    def start_match(self, difficulty: str) -> None:
        self.difficulty = difficulty
        if difficulty == "easy":
            self.destroy_limits = {"human": 4, "ai": 2}
        else:
            self.destroy_limits = {"human": 2, "ai": 3}
        self.destroy_given = {"human": 0, "ai": 0}
        self.destroy_rolls = {"human": 0, "ai": 0}
        self.human_platter = [PropCard(self.generate_platter_prop("human", i), i, self) for i in range(4)]
        self.ai_platter = [self.generate_platter_prop("ai", i) for i in range(4)]
        self.level_select = False
        self.started = True
        label = "Easy: Alpha-Beta AI" if difficulty == "easy" else "Hard: Monte Carlo + Fuzzy AI"
        self.message = f"{label}. Your turn."

    def save_screenshot(self) -> None:
        screenshot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
        os.makedirs(screenshot_dir, exist_ok=True)
        filename = f"blockwars_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = os.path.join(screenshot_dir, filename)
        pygame.image.save(self.screen, path)
        self.message = f"Screenshot saved: screenshots/{filename}"

    def grid_from_mouse(self, pos: tuple[int, int]) -> Optional[tuple[str, int, int]]:
        x, y = pos
        if GRID_TOP <= y < GRID_TOP + GRID_PIXELS:
            row = (y - GRID_TOP) // CELL_SIZE
            if HUMAN_GRID_LEFT <= x < HUMAN_GRID_LEFT + GRID_PIXELS:
                col = (x - HUMAN_GRID_LEFT) // CELL_SIZE
                return ("human", row, col)
            if AI_GRID_LEFT <= x < AI_GRID_LEFT + GRID_PIXELS:
                col = (x - AI_GRID_LEFT) // CELL_SIZE
                return ("ai", row, col)
        return None

    def grid_rect(self, owner: str, row: int, col: int) -> pygame.Rect:
        left = HUMAN_GRID_LEFT if owner == "human" else AI_GRID_LEFT
        return pygame.Rect(left + col * CELL_SIZE, GRID_TOP + row * CELL_SIZE, CELL_SIZE, CELL_SIZE)

    def board_for(self, owner: str) -> list[list[Optional[PlacedProp]]]:
        return self.human_grid if owner == "human" else self.ai_grid

    def opponent(self, owner: str) -> str:
        return "ai" if owner == "human" else "human"

    def apply_human_prop(self, prop: str, target: tuple[str, int, int]) -> bool:
        target_owner, row, col = target
        if prop in BUILD_PROPS:
            return target_owner == "human" and self.build("human", row, col, prop)
        if prop == "destroy":
            return target_owner == "ai" and self.destroy("human", row, col)
        if prop == "undo":
            return target_owner == "human" and self.undo("human", row, col)
        return False

    def build(self, owner: str, row: int, col: int, prop: str) -> bool:
        board = self.board_for(owner)
        width, height = PROP_DIMS[prop]
        if not self.can_place(owner, row, col, prop):
            return False
        placed = PlacedProp(self.next_prop_id, prop, owner, row, col, width, height)
        self.next_prop_id += 1
        for r in range(row, row + height):
            for c in range(col, col + width):
                board[r][c] = placed
        delta = PROP_COINS[prop]
        self.scores[owner] += delta
        self.histories[owner].append(MoveRecord("build", owner, (row, col), prop, coin_delta=delta))
        self.add_float(owner, row, col, f"{delta:+d}" if delta else "0", COLORS["coin"] if delta >= 0 else COLORS["red"])
        self.message = f"{owner_label(owner)} built {PROP_LABELS[prop]} {width}x{height} ({delta:+d} coins)."
        return True

    def can_place(self, owner: str, row: int, col: int, prop: str) -> bool:
        width, height = PROP_DIMS[prop]
        if row < 0 or col < 0 or row + height > GRID_SIZE or col + width > GRID_SIZE:
            return False
        board = self.board_for(owner)
        for r in range(row, row + height):
            for c in range(col, col + width):
                if board[r][c] is not None:
                    return False
        return True

    def destroy(self, owner: str, row: int, col: int) -> bool:
        target_owner = self.opponent(owner)
        board = self.board_for(target_owner)
        item = board[row][col]
        if item is None:
            return False
        self.clear_placed_prop(target_owner, item)
        self.scores[target_owner] -= 5
        self.histories[owner].append(
            MoveRecord(
                "destroy",
                owner,
                (row, col),
                item.prop,
                target_owner=target_owner,
                restored_item=item,
                target_penalty=-5,
            )
        )
        self.add_float(target_owner, row, col, "-5", COLORS["red"])
        self.message = f"{owner_label(owner)} destroyed {owner_label(target_owner)}'s {PROP_LABELS[item.prop]}."
        return True

    def undo(self, owner: str, row: int, col: int) -> bool:
        board = self.board_for(owner)
        item = board[row][col]
        if item is None:
            return False
        self.clear_placed_prop(owner, item)
        self.scores[owner] -= 2
        self.add_float(owner, row, col, "-2", COLORS["red"])
        self.message = f"{owner_label(owner)} undid {PROP_LABELS[item.prop]} (-2 coins)."
        return True

    def clear_placed_prop(self, owner: str, item: PlacedProp) -> None:
        board = self.board_for(owner)
        for r in range(item.row, item.row + item.height):
            for c in range(item.col, item.col + item.width):
                if 0 <= r < GRID_SIZE and 0 <= c < GRID_SIZE and board[r][c] is item:
                    board[r][c] = None

    def replace_human_slot(self, slot_index: int) -> None:
        self.human_platter[slot_index] = PropCard(self.generate_platter_prop("human", slot_index), slot_index, self)

    def replace_ai_slot(self, slot_index: int) -> None:
        self.ai_platter[slot_index] = self.generate_platter_prop("ai", slot_index)

    def generate_platter_prop(self, owner: str, slot_index: int) -> str:
        if slot_index == 0:
            return "undo"
        self.destroy_rolls[owner] += 1
        remaining_destroys = self.destroy_limits[owner] - self.destroy_given[owner]
        remaining_rolls = max(0, self.destroy_roll_budget - self.destroy_rolls[owner] + 1)
        should_force_destroy = remaining_destroys > 0 and remaining_rolls <= remaining_destroys
        should_bonus_destroy = remaining_destroys > 0 and random.random() < DESTROY_BONUS_CHANCE
        if should_force_destroy or should_bonus_destroy:
            self.destroy_given[owner] += 1
            return "destroy"
        return random.choice(SHUFFLED_BUILD_PROPS)

    def force_destroy_into_ai_platter(self) -> bool:
        if self.destroy_given["ai"] >= self.destroy_limits["ai"]:
            return False
        slot = random.randrange(1, 4)
        self.ai_platter[slot] = "destroy"
        self.destroy_given["ai"] += 1
        return True

    def generate_sim_platter_prop(self, slot_index: int) -> str:
        if slot_index == 0:
            return "undo"
        if random.random() < DESTROY_BONUS_CHANCE:
            return "destroy"
        return random.choice(SHUFFLED_BUILD_PROPS)

    def finish_turn(self, owner: str) -> None:
        self.turns[owner] += 1
        if self.turns["human"] >= MAX_TURNS and self.turns["ai"] >= MAX_TURNS:
            self.end_game()
            return
        if owner == "human":
            if self.turns["ai"] < MAX_TURNS:
                self.current_player = "ai"
                self.ai_pending = True
                self.ai_timer = 0.85
                self.message = f"AI is thinking ({self.difficulty.upper()})..."
            else:
                self.current_player = "human"
                self.message = "Your turn."
        else:
            self.current_player = "human"
            if self.turns["human"] < MAX_TURNS:
                self.message = "Your turn. Drag a prop onto the board."
            else:
                self.current_player = "ai"
                self.ai_pending = True
                self.ai_timer = 0.85

    def end_game(self) -> None:
        self.game_over = True
        if self.scores["human"] > self.scores["ai"]:
            self.winner_text = "Human Wins!"
        elif self.scores["ai"] > self.scores["human"]:
            self.winner_text = "AI Wins!"
        else:
            self.winner_text = "Draw!"
        self.message = "Game over."
        if self.winner_text == "Human Wins!":
            self.play_sound("victory")
        elif self.winner_text == "AI Wins!":
            self.play_sound("lost")

    def perform_ai_turn(self) -> None:
        if self.game_over or self.turns["ai"] >= MAX_TURNS:
            return
        ai_turn_number = self.turns["ai"] + 1
        scripted = AI_SCRIPT.get(ai_turn_number)
        action = None
        if scripted == "build":
            action = self.choose_ai_build_action(force_build_prop=True)
        elif scripted == "destroy":
            action = self.choose_ai_destroy_action(force_destroy_prop=True)
        elif scripted == "undo":
            action = self.choose_ai_undo_action(force_undo_prop=True)
        else:
            action = self.choose_easy_ai_action() if self.difficulty == "easy" else self.choose_hard_ai_action()

        if not action:
            action = self.choose_ai_fallback_action()
        if action:
            self.start_ai_animation(action)
        else:
            self.message = "AI had no valid move."
            self.finish_turn("ai")

    def choose_hard_ai_action(self) -> Optional[dict]:
        candidates = self.legal_actions("ai", self.ai_platter)
        if not candidates:
            return None
        scored = [(self.fuzzy_score_action(action, "ai"), action) for action in candidates]
        scored.sort(key=lambda item: item[0], reverse=True)
        top_candidates = [action for _score, action in scored[: min(8, len(scored))]]
        return max(
            top_candidates,
            key=lambda action: self.monte_carlo_value(action, rollouts=18),
        )

    def choose_easy_ai_action(self) -> Optional[dict]:
        candidates = self.legal_actions("ai", self.ai_platter)
        if not candidates:
            return None
        best_score = -10_000.0
        best_action = candidates[0]
        alpha = -10_000.0
        beta = 10_000.0
        for action in candidates:
            sim = self.snapshot_state()
            self.apply_sim_action(sim, "ai", action)
            score = self.alpha_beta(sim, depth=2, maximizing=False, alpha=alpha, beta=beta)
            if score > best_score:
                best_score = score
                best_action = action
            alpha = max(alpha, best_score)
        return best_action

    def alpha_beta(self, sim: dict, depth: int, maximizing: bool, alpha: float, beta: float) -> float:
        if depth == 0:
            return sim["scores"]["ai"] - sim["scores"]["human"]
        owner = "ai" if maximizing else "human"
        platter = [self.generate_sim_platter_prop(i) for i in range(4)]
        actions = self.legal_sim_actions(sim, owner, platter)
        if not actions:
            return sim["scores"]["ai"] - sim["scores"]["human"]
        actions = sorted(actions, key=self.sim_score_action, reverse=maximizing)[:10]
        if maximizing:
            value = -10_000.0
            for action in actions:
                child = self.copy_sim(sim)
                self.apply_sim_action(child, owner, action)
                value = max(value, self.alpha_beta(child, depth - 1, False, alpha, beta))
                alpha = max(alpha, value)
                if alpha >= beta:
                    break
            return value
        value = 10_000.0
        for action in actions:
            child = self.copy_sim(sim)
            self.apply_sim_action(child, owner, action)
            value = min(value, self.alpha_beta(child, depth - 1, True, alpha, beta))
            beta = min(beta, value)
            if alpha >= beta:
                break
        return value

    def ai_fallback(self) -> bool:
        return (
            self.ai_build_best(force_build_prop=False)
            or self.ai_destroy_best(force_destroy_prop=False)
            or self.ai_undo(force_undo_prop=False)
        )

    def choose_ai_fallback_action(self) -> Optional[dict]:
        return (
            self.choose_ai_build_action(force_build_prop=False)
            or self.choose_ai_destroy_action(force_destroy_prop=False)
            or self.choose_ai_undo_action(force_undo_prop=False)
        )

    def choose_ai_build_action(self, preferred: tuple[str, ...] = BUILD_PROPS, force_build_prop: bool = False) -> Optional[dict]:
        slot, prop = self.ai_find_build_slot(preferred, force_build_prop)
        if slot is None or prop is None:
            return None
        position = self.ai_best_build_position(prop)
        if position is None:
            return None
        row, col = position
        return {"type": "build", "prop": prop, "row": row, "col": col, "slot": slot}

    def choose_ai_destroy_action(self, force_destroy_prop: bool) -> Optional[dict]:
        if "destroy" not in self.ai_platter:
            if not force_destroy_prop:
                return None
            if not self.force_destroy_into_ai_platter():
                return None
        targets = self.occupied_props("human")
        if not targets:
            return None
        targets.sort(key=lambda item: (PROP_COINS[item.prop], item.width * item.height, item.row, item.col), reverse=True)
        item = targets[0]
        return {"type": "destroy", "prop": item.prop, "row": item.row, "col": item.col, "slot": self.ai_platter.index("destroy")}

    def choose_ai_undo_action(self, force_undo_prop: bool) -> Optional[dict]:
        if "undo" not in self.ai_platter:
            if not force_undo_prop:
                return None
            self.ai_platter[0] = "undo"
        own_props = self.occupied_props("ai")
        if not own_props:
            return None
        item = min(own_props, key=lambda placed: PROP_COINS[placed.prop])
        return {"type": "undo", "prop": item.prop, "row": item.row, "col": item.col, "slot": 0}

    def ai_build_best(self, preferred: tuple[str, ...] = BUILD_PROPS, force_build_prop: bool = False) -> bool:
        slot, prop = self.ai_find_build_slot(preferred, force_build_prop)
        if slot is None or prop is None:
            return False
        position = self.ai_best_build_position(prop)
        if position is None:
            return False
        row, col = position
        if self.build("ai", row, col, prop):
            self.replace_ai_slot(slot)
            return True
        return False

    def ai_find_build_slot(self, preferred: tuple[str, ...], force_build_prop: bool) -> tuple[Optional[int], Optional[str]]:
        candidates = [(i, prop) for i, prop in enumerate(self.ai_platter) if prop in preferred and prop in BUILD_PROPS]
        if not candidates and preferred != BUILD_PROPS:
            candidates = [(i, prop) for i, prop in enumerate(self.ai_platter) if prop in BUILD_PROPS]
        if candidates:
            candidates.sort(key=lambda pair: (PROP_COINS[pair[1]], random.random()), reverse=True)
            return candidates[0]
        if force_build_prop:
            slot = random.randrange(1, 4)
            prop = random.choice(("house", "park"))
            self.ai_platter[slot] = prop
            return slot, prop
        return None, None

    def ai_best_build_position(self, prop: str) -> Optional[tuple[int, int]]:
        positions = [(r, c) for r in range(GRID_SIZE) for c in range(GRID_SIZE) if self.can_place("ai", r, c, prop)]
        if not positions:
            return None
        center = (GRID_SIZE - 1) / 2
        positions.sort(key=lambda pos: abs(pos[0] - center) + abs(pos[1] - center))
        if prop == "street":
            positions.sort(key=lambda pos: (pos[1], abs(pos[0] - center)))
        return positions[0]

    def ai_destroy_best(self, force_destroy_prop: bool) -> bool:
        if "destroy" not in self.ai_platter:
            if not force_destroy_prop:
                return False
            if not self.force_destroy_into_ai_platter():
                return False
        targets = self.occupied_props("human")
        if not targets:
            return False
        targets.sort(key=lambda item: (PROP_COINS[item.prop], item.width * item.height, item.row, item.col), reverse=True)
        item = targets[0]
        row, col = item.row, item.col
        if self.destroy("ai", row, col):
            self.replace_ai_slot(self.ai_platter.index("destroy"))
            return True
        return False

    def ai_undo(self, force_undo_prop: bool) -> bool:
        if "undo" not in self.ai_platter:
            if not force_undo_prop:
                return False
            self.ai_platter[0] = "undo"
        own_props = self.occupied_props("ai")
        if not own_props:
            return False
        item = min(own_props, key=lambda placed: PROP_COINS[placed.prop])
        if self.undo("ai", item.row, item.col):
            self.replace_ai_slot(0)
            return True
        return False

    def execute_ai_action(self, action: dict) -> bool:
        slot = action["slot"]
        if action["type"] == "build":
            success = self.build("ai", action["row"], action["col"], action["prop"])
        elif action["type"] == "destroy":
            success = self.destroy("ai", action["row"], action["col"])
        elif action["type"] == "undo":
            success = self.undo("ai", action["row"], action["col"])
        else:
            success = False
        if success:
            self.replace_ai_slot(slot)
        return success

    def start_ai_animation(self, action: dict) -> None:
        slot = action["slot"]
        prop = self.ai_platter[slot]
        start = pygame.Vector2(self.ai_slot_rect(slot).center)
        end = pygame.Vector2(self.ai_action_target_rect(action).center)
        self.ai_animation = AIAnimation(action=action, prop=prop, slot=slot, start=start, end=end)
        self.message = f"AI dragging {PROP_LABELS[prop]}..."

    def update_ai_animation(self, dt: float) -> None:
        if not self.ai_animation:
            return
        self.ai_animation.elapsed += dt
        if self.ai_animation.elapsed >= self.ai_animation.duration:
            action = self.ai_animation.action
            prop = self.ai_animation.prop
            self.ai_animation = None
            self.execute_ai_action(action)
            self.play_drop_sounds(prop)
            self.finish_turn("ai")

    def ai_action_target_rect(self, action: dict) -> pygame.Rect:
        if action["type"] == "build":
            width, height = PROP_DIMS[action["prop"]]
            rect = self.grid_rect("ai", action["row"], action["col"])
            return pygame.Rect(rect.left, rect.top, width * CELL_SIZE, height * CELL_SIZE)
        if action["type"] == "destroy":
            item = self.human_grid[action["row"]][action["col"]]
            if item:
                return self.prop_rect("human", item)
            return self.grid_rect("human", action["row"], action["col"])
        if action["type"] == "undo":
            item = self.ai_grid[action["row"]][action["col"]]
            if item:
                return self.prop_rect("ai", item)
            return self.grid_rect("ai", action["row"], action["col"])
        return self.grid_rect("ai", 0, 0)

    def legal_actions(self, owner: str, platter: list[str]) -> list[dict]:
        actions = []
        opponent = self.opponent(owner)
        for slot, prop in enumerate(platter):
            if prop in BUILD_PROPS:
                for row in range(GRID_SIZE):
                    for col in range(GRID_SIZE):
                        if self.can_place(owner, row, col, prop):
                            actions.append({"type": "build", "prop": prop, "row": row, "col": col, "slot": slot})
            elif prop == "destroy":
                for item in self.occupied_props(opponent):
                    actions.append({"type": "destroy", "prop": item.prop, "row": item.row, "col": item.col, "slot": slot})
            elif prop == "undo":
                for item in self.occupied_props(owner):
                    actions.append({"type": "undo", "prop": item.prop, "row": item.row, "col": item.col, "slot": slot})
        return actions

    def fuzzy_score_action(self, action: dict, owner: str) -> float:
        if action["type"] == "build":
            prop = action["prop"]
            width, height = PROP_DIMS[prop]
            area = width * height
            coin_gain = PROP_COINS[prop] / 3
            free_after = (self.free_cell_count(owner) - area) / (GRID_SIZE * GRID_SIZE)
            footprint_value = area / 9
            space_risk = 1 - free_after
            center = (GRID_SIZE - 1) / 2
            center_fit = 1 - min(1, (abs(action["row"] - center) + abs(action["col"] - center)) / 6)
            return 4.0 * coin_gain + 1.2 * footprint_value + 0.9 * center_fit - 1.4 * space_risk
        if action["type"] == "destroy":
            target_value = PROP_COINS[action["prop"]] / 3
            width, height = PROP_DIMS[action["prop"]]
            area_pressure = (width * height) / 9
            return 3.4 + 2.0 * target_value + 1.0 * area_pressure
        if action["type"] == "undo":
            prop = action["prop"]
            width, height = PROP_DIMS[prop]
            low_value = 1 - max(0, PROP_COINS[prop]) / 3
            frees_space = (width * height) / 9
            return 0.9 * low_value + 1.0 * frees_space - 2.0
        return -999

    def monte_carlo_value(self, action: dict, rollouts: int = 18) -> float:
        total = 0.0
        for _ in range(rollouts):
            total += self.simulate_rollout(action)
        return total / max(1, rollouts)

    def simulate_rollout(self, first_action: dict) -> float:
        sim = self.snapshot_state()
        self.apply_sim_action(sim, "ai", first_action)
        ai_turn = self.turns["ai"] + 1
        human_turn = self.turns["human"]
        while ai_turn < MAX_TURNS or human_turn < MAX_TURNS:
            if human_turn < MAX_TURNS:
                self.apply_random_sim_action(sim, "human")
                human_turn += 1
            if ai_turn < MAX_TURNS:
                self.apply_random_sim_action(sim, "ai")
                ai_turn += 1
        return sim["scores"]["ai"] - sim["scores"]["human"]

    def snapshot_state(self) -> dict:
        props = {"human": [], "ai": []}
        for owner in ("human", "ai"):
            for item in self.occupied_props(owner):
                props[owner].append((item.prop, item.row, item.col, item.width, item.height))
        return {"props": props, "scores": dict(self.scores)}

    def copy_sim(self, sim: dict) -> dict:
        return {
            "props": {
                "human": list(sim["props"]["human"]),
                "ai": list(sim["props"]["ai"]),
            },
            "scores": dict(sim["scores"]),
        }

    def apply_random_sim_action(self, sim: dict, owner: str) -> None:
        platter = [self.generate_sim_platter_prop(i) for i in range(4)]
        actions = self.legal_sim_actions(sim, owner, platter)
        if actions:
            action = max(random.sample(actions, min(len(actions), 6)), key=lambda candidate: self.sim_score_action(candidate))
            self.apply_sim_action(sim, owner, action)

    def legal_sim_actions(self, sim: dict, owner: str, platter: list[str]) -> list[dict]:
        actions = []
        opponent = self.opponent(owner)
        occupied = self.sim_occupied(sim, owner)
        opponent_props = sim["props"][opponent]
        own_props = sim["props"][owner]
        for slot, prop in enumerate(platter):
            if prop in BUILD_PROPS:
                width, height = PROP_DIMS[prop]
                for row in range(GRID_SIZE - height + 1):
                    for col in range(GRID_SIZE - width + 1):
                        cells = {(r, c) for r in range(row, row + height) for c in range(col, col + width)}
                        if not occupied.intersection(cells):
                            actions.append({"type": "build", "prop": prop, "row": row, "col": col, "slot": slot})
            elif prop == "destroy":
                for item in opponent_props:
                    actions.append({"type": "destroy", "prop": item[0], "row": item[1], "col": item[2], "slot": slot})
            elif prop == "undo":
                for item in own_props:
                    actions.append({"type": "undo", "prop": item[0], "row": item[1], "col": item[2], "slot": slot})
        return actions

    def apply_sim_action(self, sim: dict, owner: str, action: dict) -> None:
        if action["type"] == "build":
            prop = action["prop"]
            width, height = PROP_DIMS[prop]
            sim["props"][owner].append((prop, action["row"], action["col"], width, height))
            sim["scores"][owner] += PROP_COINS[prop]
        elif action["type"] == "destroy":
            opponent = self.opponent(owner)
            self.remove_sim_prop_at(sim, opponent, action["row"], action["col"])
            sim["scores"][opponent] -= 5
        elif action["type"] == "undo":
            if self.remove_sim_prop_at(sim, owner, action["row"], action["col"]):
                sim["scores"][owner] -= 2

    def sim_score_action(self, action: dict) -> float:
        if action["type"] == "build":
            width, height = PROP_DIMS[action["prop"]]
            return PROP_COINS[action["prop"]] + (width * height * 0.1)
        if action["type"] == "destroy":
            return 4 + PROP_COINS[action["prop"]]
        if action["type"] == "undo":
            return -1
        return 0

    def sim_occupied(self, sim: dict, owner: str) -> set[tuple[int, int]]:
        occupied = set()
        for _prop, row, col, width, height in sim["props"][owner]:
            for r in range(row, row + height):
                for c in range(col, col + width):
                    occupied.add((r, c))
        return occupied

    def remove_sim_prop_at(self, sim: dict, owner: str, row: int, col: int) -> bool:
        for index, (_prop, item_row, item_col, width, height) in enumerate(sim["props"][owner]):
            if item_row <= row < item_row + height and item_col <= col < item_col + width:
                sim["props"][owner].pop(index)
                return True
        return False

    def free_cell_count(self, owner: str) -> int:
        board = self.board_for(owner)
        return sum(1 for row in board for cell in row if cell is None)

    def occupied_cells(self, owner: str) -> list[tuple[int, int, PlacedProp]]:
        board = self.board_for(owner)
        return [(r, c, board[r][c]) for r in range(GRID_SIZE) for c in range(GRID_SIZE) if board[r][c] is not None]

    def occupied_props(self, owner: str) -> list[PlacedProp]:
        seen = set()
        props = []
        for _row, _col, item in self.occupied_cells(owner):
            if item.id not in seen:
                seen.add(item.id)
                props.append(item)
        return props

    def add_float(self, owner: str, row: int, col: int, text: str, color: tuple[int, int, int]) -> None:
        rect = self.grid_rect(owner, row, col)
        self.floating_texts.append(FloatingText(text, pygame.Vector2(rect.center), color))

    def add_center_float(self, owner: str, text: str, color: tuple[int, int, int]) -> None:
        left = HUMAN_GRID_LEFT if owner == "human" else AI_GRID_LEFT
        pos = pygame.Vector2(left + GRID_PIXELS // 2, GRID_TOP + GRID_PIXELS // 2)
        self.floating_texts.append(FloatingText(text, pos, color))

    def draw(self) -> None:
        self.draw_background()
        if not self.started and not self.level_select:
            self.draw_start_screen()
        elif self.level_select:
            self.draw_level_screen()
        else:
            self.draw_game_screen()
        pygame.display.flip()

    def draw_background(self) -> None:
        self.screen.fill(COLORS["grass"])
        for y in range(0, SCREEN_HEIGHT, 46):
            pygame.draw.line(self.screen, (139, 189, 122), (0, y), (SCREEN_WIDTH, y), 1)
        for _ in range(38):
            x = random.Random(_).randrange(0, SCREEN_WIDTH)
            y = random.Random(_ * 7).randrange(0, SCREEN_HEIGHT)
            pygame.draw.arc(self.screen, COLORS["grass_dark"], (x, y, 20, 12), 0.2, 2.7, 1)

    def draw_start_screen(self) -> None:
        title = self.font_title.render("BlockWars", True, COLORS["text"])
        subtitle = self.font_medium.render("Human vs AI city sandbox", True, COLORS["muted"])
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 310)))
        self.screen.blit(subtitle, subtitle.get_rect(center=(SCREEN_WIDTH // 2, 370)))
        self.draw_button(self.play_button_rect(), "PLAY", COLORS["green"])
        hint = self.font_small.render("Drag random props, build your block, disrupt the AI, and win after 10 turns.", True, COLORS["text"])
        self.screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, 640)))

    def draw_level_screen(self) -> None:
        title = self.font_title.render("Choose Level", True, COLORS["text"])
        subtitle = self.font_medium.render("Pick the AI strategy you want to face", True, COLORS["muted"])
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 290)))
        self.screen.blit(subtitle, subtitle.get_rect(center=(SCREEN_WIDTH // 2, 350)))
        self.draw_button(self.easy_button_rect(), "EASY", COLORS["human"])
        self.draw_button(self.hard_button_rect(), "HARD", COLORS["red"])
        easy = self.font_small.render("Alpha-Beta pruning", True, COLORS["text"])
        hard = self.font_small.render("Monte Carlo + Fuzzy", True, COLORS["text"])
        self.screen.blit(easy, easy.get_rect(center=(self.easy_button_rect().centerx, 620)))
        self.screen.blit(hard, hard.get_rect(center=(self.hard_button_rect().centerx, 620)))

    def draw_game_screen(self) -> None:
        self.draw_headers()
        self.draw_road()
        self.draw_board("human")
        self.draw_board("ai")
        self.draw_ai_platter()
        self.draw_platter()
        self.draw_status()
        for text in self.floating_texts:
            text.draw(self.screen, self.font_medium)
        if self.ai_animation:
            self.draw_ai_animation()
        if self.dragged_card:
            self.draw_drop_feedback()
            self.dragged_card.draw(self.screen)
        if self.game_over:
            self.draw_game_over()

    def draw_headers(self) -> None:
        self.draw_player_header("human", HUMAN_GRID_LEFT, "HUMAN PLAYER")
        self.draw_player_header("ai", AI_GRID_LEFT, "AI PLAYER")

    def draw_player_header(self, owner: str, left: int, title: str) -> None:
        header = pygame.Rect(left, 40, GRID_PIXELS, 96)
        pygame.draw.rect(self.screen, COLORS["panel_shadow"], header.move(6, 7), border_radius=24)
        pygame.draw.rect(self.screen, COLORS["panel"], header, border_radius=24)
        pygame.draw.rect(self.screen, COLORS["slot_border"], header, width=3, border_radius=24)
        title_surf = self.font_big.render(title, True, COLORS["text"])
        self.screen.blit(title_surf, (left + 25, 57))
        self.draw_coin_badge(left + 28, 99, self.scores[owner])
        turns = self.font_small.render(f"Turn {self.turns[owner]}/{MAX_TURNS}", True, COLORS["muted"])
        self.screen.blit(turns, (left + GRID_PIXELS - 132, 106))

    def draw_coin_badge(self, x: int, y: int, value: int) -> None:
        rect = pygame.Rect(x, y, 148, 45)
        pygame.draw.rect(self.screen, (69, 121, 150), rect, border_radius=18)
        pygame.draw.circle(self.screen, COLORS["coin"], (x + 26, y + 22), 16)
        pygame.draw.circle(self.screen, COLORS["coin_dark"], (x + 26, y + 22), 16, width=3)
        coin_text = self.font_tiny.render("$", True, COLORS["coin_dark"])
        self.screen.blit(coin_text, coin_text.get_rect(center=(x + 26, y + 22)))
        value_text = self.font_big.render(f"{value:+d}", True, COLORS["white"])
        self.screen.blit(value_text, (x + 53, y + 3))

    def draw_road(self) -> None:
        road = pygame.Rect(ROAD_LEFT, 0, ROAD_WIDTH, SCREEN_HEIGHT)
        pygame.draw.rect(self.screen, COLORS["road_edge"], road.inflate(24, 0))
        pygame.draw.rect(self.screen, COLORS["road"], road)
        pygame.draw.line(self.screen, COLORS["road_center"], (ROAD_LEFT + ROAD_WIDTH // 2, 0), (ROAD_LEFT + ROAD_WIDTH // 2, SCREEN_HEIGHT), 5)
        for y in range(24, SCREEN_HEIGHT, 95):
            pygame.draw.rect(self.screen, COLORS["road_line"], (ROAD_LEFT + 52, y, 8, 46), border_radius=4)
            pygame.draw.rect(self.screen, COLORS["road_line"], (ROAD_LEFT + ROAD_WIDTH - 60, y, 8, 46), border_radius=4)

    def draw_board(self, owner: str) -> None:
        left = HUMAN_GRID_LEFT if owner == "human" else AI_GRID_LEFT
        board_rect = pygame.Rect(left - 18, GRID_TOP - 18, GRID_PIXELS + 36, GRID_PIXELS + 36)
        pygame.draw.rect(self.screen, COLORS["panel_shadow"], board_rect.move(6, 7), border_radius=10)
        pygame.draw.rect(self.screen, (189, 154, 126), board_rect, border_radius=10)

        board = self.board_for(owner)
        for row in range(GRID_SIZE):
            for col in range(GRID_SIZE):
                rect = self.grid_rect(owner, row, col)
                color = COLORS["grid_alt"] if (row + col) % 2 == 0 else COLORS["grid"]
                pygame.draw.rect(self.screen, color, rect)
                pygame.draw.rect(self.screen, COLORS["grid_line"], rect, width=2)
        for item in self.occupied_props(owner):
            self.draw_grid_item(item)

    def prop_rect(self, owner: str, item: PlacedProp) -> pygame.Rect:
        rect = self.grid_rect(owner, item.row, item.col)
        return pygame.Rect(rect.left, rect.top, item.width * CELL_SIZE, item.height * CELL_SIZE)

    def draw_grid_item(self, item: PlacedProp) -> None:
        rect = self.prop_rect(item.owner, item).inflate(-8, -8)
        pygame.draw.rect(self.screen, (255, 255, 255), rect, border_radius=10)
        pygame.draw.rect(self.screen, COLORS["slot_border"], rect, width=2, border_radius=10)
        image = self.assets.get(item.prop)
        if image:
            scaled = self.fit_image(image, (rect.width - 10, rect.height - 10))
            self.screen.blit(scaled, scaled.get_rect(center=rect.center))
        else:
            pygame.draw.circle(self.screen, COLORS["coin"], rect.center, 24)

    def draw_platter(self) -> None:
        panel = pygame.Rect(220, PLATTER_TOP - 18, 960, PLATTER_HEIGHT)
        pygame.draw.rect(self.screen, COLORS["panel_shadow"], panel.move(7, 8), border_radius=28)
        pygame.draw.rect(self.screen, COLORS["panel"], panel, border_radius=28)
        pygame.draw.rect(self.screen, COLORS["slot_border"], panel, width=3, border_radius=28)
        label = self.font_medium.render("YOUR PROP PLATTER", True, COLORS["text"])
        self.screen.blit(label, (245, PLATTER_TOP + 34))
        for card in self.human_platter:
            if card is not self.dragged_card:
                card.draw(self.screen)

    def ai_slot_rect(self, slot_index: int) -> pygame.Rect:
        return pygame.Rect(1010 + slot_index * 74, 140, 62, 48)

    def draw_ai_platter(self) -> None:
        label = self.font_tiny.render("AI PLATTER", True, COLORS["text"])
        self.screen.blit(label, (AI_GRID_LEFT + 24, 153))
        for index, prop in enumerate(self.ai_platter):
            rect = self.ai_slot_rect(index)
            if self.ai_animation and self.ai_animation.slot == index:
                self.draw_mini_prop_card(rect, prop, dimmed=True)
            else:
                self.draw_mini_prop_card(rect, prop)

    def draw_mini_prop_card(self, rect: pygame.Rect, prop: str, dimmed: bool = False) -> None:
        pygame.draw.rect(self.screen, COLORS["panel_shadow"], rect.move(3, 4), border_radius=10)
        pygame.draw.rect(self.screen, COLORS["slot"], rect, border_radius=10)
        pygame.draw.rect(self.screen, COLORS["slot_border"], rect, width=2, border_radius=10)
        image = self.assets.get(prop)
        if image:
            scaled = self.fit_image(image, (rect.width - 14, rect.height - 18))
            if dimmed:
                scaled = scaled.copy()
                scaled.set_alpha(90)
            self.screen.blit(scaled, scaled.get_rect(center=(rect.centerx, rect.centery - 4)))
        text = self.font_tiny.render(PROP_LABELS[prop][:6], True, COLORS["muted"])
        self.screen.blit(text, text.get_rect(center=(rect.centerx, rect.bottom - 7)))

    def draw_ai_animation(self) -> None:
        if not self.ai_animation:
            return
        t = min(1.0, self.ai_animation.elapsed / self.ai_animation.duration)
        eased = 1 - (1 - t) * (1 - t)
        pos = self.ai_animation.start.lerp(self.ai_animation.end, eased)
        rect = pygame.Rect(0, 0, 92, 82)
        rect.center = (int(pos.x), int(pos.y))
        self.draw_mini_prop_card(rect, self.ai_animation.prop)

    def draw_status(self) -> None:
        rect = pygame.Rect(410, 147, 580, 36)
        pygame.draw.rect(self.screen, (248, 237, 209), rect, border_radius=12)
        pygame.draw.rect(self.screen, COLORS["slot_border"], rect, width=2, border_radius=12)
        status = self.font_small.render(self.message, True, COLORS["text"])
        self.screen.blit(status, status.get_rect(center=rect.center))

    def draw_drop_feedback(self) -> None:
        if not self.dragged_card or not self.hover_target:
            return
        owner, row, col = self.hover_target
        prop = self.dragged_card.prop
        valid = False
        highlight = self.grid_rect(owner, row, col)
        if prop in BUILD_PROPS:
            valid = owner == "human" and self.can_place("human", row, col, prop)
            width, height = PROP_DIMS[prop]
            highlight = pygame.Rect(highlight.left, highlight.top, width * CELL_SIZE, height * CELL_SIZE)
        elif prop == "destroy":
            valid = owner == "ai" and self.ai_grid[row][col] is not None
            if self.ai_grid[row][col]:
                highlight = self.prop_rect("ai", self.ai_grid[row][col])
        elif prop == "undo":
            valid = owner == "human" and self.human_grid[row][col] is not None
            if owner == "human" and self.human_grid[row][col]:
                highlight = self.prop_rect("human", self.human_grid[row][col])
        color = COLORS["valid"] if valid else COLORS["invalid"]
        overlay = pygame.Surface((highlight.width, highlight.height), pygame.SRCALPHA)
        overlay.fill((*color, 95))
        self.screen.blit(overlay, highlight)
        pygame.draw.rect(self.screen, color, highlight, width=4)

    def draw_game_over(self) -> None:
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((20, 20, 24, 165))
        self.screen.blit(overlay, (0, 0))
        modal = pygame.Rect(SCREEN_WIDTH // 2 - 260, 300, 520, 360)
        pygame.draw.rect(self.screen, COLORS["panel_shadow"], modal.move(8, 9), border_radius=26)
        pygame.draw.rect(self.screen, COLORS["panel"], modal, border_radius=26)
        pygame.draw.rect(self.screen, COLORS["slot_border"], modal, width=4, border_radius=26)
        title = self.font_title.render(self.winner_text, True, COLORS["text"])
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 375)))
        score = self.font_medium.render(
            f"Human {self.scores['human']}  |  AI {self.scores['ai']}",
            True,
            COLORS["muted"],
        )
        self.screen.blit(score, score.get_rect(center=(SCREEN_WIDTH // 2, 455)))
        self.draw_button(self.restart_button_rect(), "RESTART", COLORS["orange"])
        esc = self.font_small.render("Press Esc to quit", True, COLORS["muted"])
        self.screen.blit(esc, esc.get_rect(center=(SCREEN_WIDTH // 2, 665)))

    def draw_button(self, rect: pygame.Rect, text: str, color: tuple[int, int, int]) -> None:
        pygame.draw.rect(self.screen, COLORS["panel_shadow"], rect.move(5, 6), border_radius=20)
        pygame.draw.rect(self.screen, color, rect, border_radius=20)
        pygame.draw.rect(self.screen, COLORS["white"], rect, width=3, border_radius=20)
        label = self.font_big.render(text, True, COLORS["white"])
        self.screen.blit(label, label.get_rect(center=rect.center))


def owner_label(owner: str) -> str:
    return "Human" if owner == "human" else "AI"


if __name__ == "__main__":
    BlockWarsGame().run()
