return {
  -- Syntax highlighting.
  {
    "nvim-treesitter/nvim-treesitter",
    build = ":TSUpdate",
    config = function()
      require("nvim-treesitter.configs").setup({
        ensure_installed = { "lua", "vim", "vimdoc", "bash", "python", "go", "json", "yaml", "markdown" },
        auto_install = true,
        highlight = { enable = true },
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
}
