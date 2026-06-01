import unittest
from app import check_winner

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
    
    def test_no_winner(self):
        board = ['X', 'O', 'X', 'X', 'O', 'O', 'O', 'X', 'X']
        self.assertIsNone(check_winner(board))
    
    def test_empty_board(self):
        board = [''] * 9
        self.assertIsNone(check_winner(board))

if __name__ == '__main__':
    unittest.main()
