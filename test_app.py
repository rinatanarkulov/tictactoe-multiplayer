import unittest
from app import check_winner, create_game_data, games

class TestTicTacToe(unittest.TestCase):
    
    def test_winner_row(self):
        board = ['X', 'X', 'X', '', '', '', '', '', '']
        self.assertEqual(check_winner(board), 'X')
    
    def test_winner_column(self):
        board = ['O', '', '', 'O', '', '', 'O', '', '']
        self.assertEqual(check_winner(board), 'O')
    
    def test_winner_diagonal(self):
        board = ['X', '', '', '', 'X', '', '', '', 'X']
        self.assertEqual(check_winner(board), 'X')
    
    def test_draw(self):
        board = ['X', 'O', 'X', 'X', 'O', 'O', 'O', 'X', 'X']
        self.assertIsNone(check_winner(board))
    
    def test_no_winner_yet(self):
        board = ['X', '', '', '', 'O', '', '', '', '']
        self.assertIsNone(check_winner(board))
    
    def test_create_game(self):
        game_id = create_game_data()
        self.assertEqual(len(game_id), 4)
        self.assertIn(game_id, games)

if __name__ == '__main__':
    unittest.main()
