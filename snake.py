import pygame
import random
import time

class Snake:
    def __init__(self):
        pygame.init()
        self.white = (255, 255, 255)
        self.yellow = (255, 255, 102)
        self.black = (0, 0, 0)
        self.red = (213, 50, 80)
        self.green = (0, 255, 0)
        self.blue = (50, 153, 213)
        self.dis_width = 800
        self.dis_height = 600
        self.dis = pygame.display.set_mode((self.dis_width, self.dis_height))
        pygame.display.set_caption('Snake Game')
        self.clock = pygame.time.Clock()
        self.snake_block = 10
        self.snake_speed = 15
        self.font_style = pygame.font.SysFont('bahnschrift', 25)
        self.score_font = pygame.font.SysFont('comicsansms', 35)
        self.game_over = False
        self.game_close = False
        self.x1 = self.dis_width / 2
        self.y1 = self.dis_height / 2
        self.x1_change = 0
        self.y1_change = 0
        self.snake_List = []
        self.Length_of_snake = 1
        self.foodx = round(random.randrange(0, self.dis_width - self.snake_block) / 10.0) * 10.0
        self.foody = round(random.randrange(0, self.dis_height - self.snake_block) / 10.0) * 10.0
        self.your_score = 0
    def snake(self, snake_block, snake_List):
        for x in snake_List:
            pygame.draw.rect(self.dis, self.green, [x[0], x[1], snake_block, snake_block])
    def message(self, msg, color):
        mesg = self.font_style.render(msg, True, color)
        self.dis.blit(mesg, [self.dis_width / 6, self.dis_height / 3])
    def your_score(self, score, color):
        value = self.score_font.render(score, True, color)
        self.dis.blit(value, [0, 0])

def main():
    game = Snake()
    game.run_game()

if __name__ == "__main__":
    main()
    def run_game(self):
        while not self.game_over:
            while self.game_close == True:
                self.dis.fill(self.black)
                self.message("You Lost! Press Q-Quit or C-Play Again", self.red)
                self.your_score("Your Score: ", self.your_score, self.white)
                pygame.display.update()
                for event in pygame.event.get():
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_q:
                            self.game_over = True
                            self.game_close = False
                        if event.key == pygame.K_c:
                            self.__init__()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.game_over = True
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_LEFT and self.x1_change == 0:
                        self.x1_change = -self.snake_block
                        self.y1_change = 0
                    elif event.key == pygame.K_RIGHT and self.x1_change == 0:
                        self.x1_change = self.snake_block
                        self.y1_change = 0
                    elif event.key == pygame.K_UP and self.y1_change == 0:
                        self.y1_change = -self.snake_block
                        self.x1_change = 0
                    elif event.key == pygame.K_DOWN and self.y1_change == 0:
                        self.y1_change = self.snake_block
                        self.x1_change = 0
            if self.x1 >= self.dis_width or self.x1 < 0 or self.y1 >= self.dis_height or self.y1 < 0:
                self.game_close = True
            self.x1 += self.x1_change
            self.y1 += self.y1_change
            self.dis.fill(self.black)
            pygame.draw.rect(self.dis, self.green, [self.foodx, self.foody, self.snake_block, self.snake_block])
            snake_Head = []
            snake_Head.append(self.x1)
            snake_Head.append(self.y1)
            self.snake_List.append(snake_Head)
            if len(self.snake_List) > self.Length_of_snake:
                del self.snake_List[0]
            for x in self.snake_List[:-1]:
                if x == snake_Head:
                    self.game_close = True
            self.snake(self.snake_block, self.snake_List)
            self.your_score("Your Score: ", self.your_score, self.white)
            pygame.display.update()
            if self.x1 == self.foodx and self.y1 == self.foody:
                self.foodx = round(random.randrange(0, self.dis_width - self.snake_block) / 10.0) * 10.0
                self.foody = round(random.randrange(0, self.dis_height - self.snake_block) / 10.0) * 10.0
                self.Length_of_snake += 1
                self.your_score += 1
            self.clock.tick(self.snake_speed)
        pygame.quit()
        quit()
    def your_score(self, score_text, score_value, color):
        value = self.score_font.render(f"{score_text}{score_value}", True, color)
        self.dis.blit(value, [0, 0])
