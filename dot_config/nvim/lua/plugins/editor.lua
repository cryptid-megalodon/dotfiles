local parsers = { "lua", "vim", "vimdoc", "bash", "python", "go", "json", "yaml", "markdown" }

-- nvim-treesitter's main branch is a rewrite that needs nvim 0.12+ and the
-- tree-sitter CLI. Older nvim (e.g. apt on Linux) stays on the frozen master
-- branch and its configs module.
local ts_main = vim.fn.has("nvim-0.12") == 1

return {
  -- Syntax highlighting.
  {
    "nvim-treesitter/nvim-treesitter",
    branch = ts_main and "main" or "master",
    lazy = false,
    build = ":TSUpdate",
    config = function()
      if not ts_main then
        require("nvim-treesitter.configs").setup({
          ensure_installed = parsers,
          auto_install = true,
          highlight = { enable = true },
        })
        return
      end

      local ts = require("nvim-treesitter")
      ts.install(parsers)
      local available = ts.get_available()
      vim.api.nvim_create_autocmd("FileType", {
        callback = function(args)
          local lang = vim.treesitter.language.get_lang(args.match)
          if not lang then
            return
          end
          -- Highlight if the parser is installed; otherwise install it if
          -- nvim-treesitter knows it (highlighting starts on the next open).
          if not pcall(vim.treesitter.start, args.buf, lang) and vim.tbl_contains(available, lang) then
            ts.install(lang)
          end
        end,
      })
    end,
  },
  -- Fuzzy finder.
  {
    "nvim-telescope/telescope.nvim",
    dependencies = { "nvim-lua/plenary.nvim" },
    keys = {
      { "<leader>f", "<cmd>Telescope find_files<CR>", desc = "Find files" },
      { "<leader>g", "<cmd>Telescope live_grep<CR>", desc = "Grep" },
      { "<leader>b", "<cmd>Telescope buffers<CR>", desc = "Buffers" },
    },
  },
  -- C-h/j/k/l moves across nvim splits and tmux panes (see ~/.tmux.conf).
  {
    "christoomey/vim-tmux-navigator",
    cmd = { "TmuxNavigateLeft", "TmuxNavigateDown", "TmuxNavigateUp", "TmuxNavigateRight" },
    keys = {
      { "<C-h>", "<cmd>TmuxNavigateLeft<CR>", desc = "Window/pane left" },
      { "<C-j>", "<cmd>TmuxNavigateDown<CR>", desc = "Window/pane down" },
      { "<C-k>", "<cmd>TmuxNavigateUp<CR>", desc = "Window/pane up" },
      { "<C-l>", "<cmd>TmuxNavigateRight<CR>", desc = "Window/pane right" },
    },
  },
}
