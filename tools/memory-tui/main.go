package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/list"
	"github.com/charmbracelet/bubbles/textarea"
	"github.com/charmbracelet/bubbles/textinput"
	"github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

// API Models
type Memory struct {
	ID        string                 `json:"id"`
	Memory    string                 `json:"memory"`    // mem0 uses "memory" not "content"
	Hash      string                 `json:"hash"`      // mem0 specific field
	CreatedAt string                 `json:"created_at"`
	UpdatedAt *string                `json:"updated_at"` // Can be null
	UserID    string                 `json:"user_id"`    // mem0 specific field
	Metadata  map[string]interface{} `json:"metadata"`
}

type MemoryResults struct {
	Results []Memory `json:"results"`
}

type APIResponse struct {
	Status  string        `json:"status"`
	Results MemoryResults `json:"results"` // Nested structure
	Result  Memory        `json:"result"`
	Count   int           `json:"count"`
	Error   string        `json:"error"`
}

// API Client
type MemoryAPI struct {
	BaseURL string
	Client  *http.Client
}

func NewMemoryAPI(baseURL string) *MemoryAPI {
	return &MemoryAPI{
		BaseURL: baseURL,
		Client:  &http.Client{Timeout: 30 * time.Second},
	}
}

func (api *MemoryAPI) GetAllMemories() ([]Memory, error) {
	resp, err := api.Client.Get(api.BaseURL + "/memories")
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var apiResp APIResponse
	if err := json.NewDecoder(resp.Body).Decode(&apiResp); err != nil {
		return nil, err
	}

	if apiResp.Error != "" {
		return nil, fmt.Errorf("API error: %s", apiResp.Error)
	}

	return apiResp.Results.Results, nil
}

func (api *MemoryAPI) GetMemory(id string) (Memory, error) {
	resp, err := api.Client.Get(api.BaseURL + "/memory/" + id)
	if err != nil {
		return Memory{}, err
	}
	defer resp.Body.Close()

	var apiResp APIResponse
	if err := json.NewDecoder(resp.Body).Decode(&apiResp); err != nil {
		return Memory{}, err
	}

	if apiResp.Error != "" {
		return Memory{}, fmt.Errorf("API error: %s", apiResp.Error)
	}

	return apiResp.Result, nil
}

func (api *MemoryAPI) AddMemory(text string, metadata map[string]interface{}) error {
	payload := map[string]interface{}{
		"text":     text,
		"metadata": metadata,
	}

	jsonData, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	resp, err := api.Client.Post(api.BaseURL+"/add", "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	var apiResp APIResponse
	if err := json.NewDecoder(resp.Body).Decode(&apiResp); err != nil {
		return err
	}

	if apiResp.Error != "" {
		return fmt.Errorf("API error: %s", apiResp.Error)
	}

	return nil
}

func (api *MemoryAPI) SearchMemories(query string, limit int) ([]Memory, error) {
	payload := map[string]interface{}{
		"query": query,
		"limit": limit,
	}

	jsonData, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}

	resp, err := api.Client.Post(api.BaseURL+"/search", "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var apiResp APIResponse
	if err := json.NewDecoder(resp.Body).Decode(&apiResp); err != nil {
		return nil, err
	}

	if apiResp.Error != "" {
		return nil, fmt.Errorf("API error: %s", apiResp.Error)
	}

	return apiResp.Results.Results, nil
}

func (api *MemoryAPI) DeleteMemory(id string) error {
	req, err := http.NewRequest("DELETE", api.BaseURL+"/delete/"+id, nil)
	if err != nil {
		return err
	}

	resp, err := api.Client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	var apiResp APIResponse
	if err := json.NewDecoder(resp.Body).Decode(&apiResp); err != nil {
		return err
	}

	if apiResp.Error != "" {
		return fmt.Errorf("API error: %s", apiResp.Error)
	}

	return nil
}

// Styles
var (
	titleStyle = lipgloss.NewStyle().
			Foreground(lipgloss.Color("#FFFDF5")).
			Background(lipgloss.Color("#25A065")).
			Padding(0, 1)

	selectedItemStyle = lipgloss.NewStyle().
				Foreground(lipgloss.Color("#EE6FF8"))

	helpStyle = lipgloss.NewStyle().
			Foreground(lipgloss.Color("#626262"))

	promptBoxStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(lipgloss.Color("#874BFD")).
			Padding(0, 1)

	promptBoxFocusedStyle = lipgloss.NewStyle().
				Border(lipgloss.RoundedBorder()).
				BorderForeground(lipgloss.Color("#F25D94")).
				Padding(0, 1)

	contentBoxStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(lipgloss.Color("#626262"))

	contentBoxFocusedStyle = lipgloss.NewStyle().
				Border(lipgloss.RoundedBorder()).
				BorderForeground(lipgloss.Color("#874BFD"))

	modalStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(lipgloss.Color("#F25D94")).
			Background(lipgloss.Color("#1a1a1a")).
			Padding(1, 2).
			Margin(1, 2)

	overlayStyle = lipgloss.NewStyle().
			Background(lipgloss.Color("#000000")).
			Foreground(lipgloss.Color("#ffffff"))
)

// List Item for memories
type memoryItem struct {
	memory Memory
}

func (i memoryItem) FilterValue() string { return i.memory.Memory }
func (i memoryItem) Title() string       { return truncateString(i.memory.Memory, 50) }
func (i memoryItem) Description() string {
	return fmt.Sprintf("ID: %s | Created: %s", 
		truncateString(i.memory.ID, 20), 
		formatTime(i.memory.CreatedAt))
}

func truncateString(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen-3] + "..."
}

func formatTime(timeStr string) string {
	if timeStr == "" {
		return "Unknown"
	}
	t, err := time.Parse(time.RFC3339, timeStr)
	if err != nil {
		return timeStr[:10] // Return first 10 chars if parsing fails
	}
	return t.Format("2006-01-02 15:04")
}

// Application states
type viewState int

const (
	listView viewState = iota
	detailView
	addView
	searchView
	confirmDeleteView
)

// Focus states for tab navigation
type focusState int

const (
	focusContent focusState = iota
	focusPrompt
)

// Main model
type model struct {
	api           *MemoryAPI
	state         viewState
	focus         focusState
	list          list.Model
	memories      []Memory
	currentMem    Memory
	textInput     textinput.Model
	textArea      textarea.Model
	searchInput   textinput.Model
	promptInput   textinput.Model
	loading       bool
	message       string
	err           error
	width         int
	height        int
	memToDelete   Memory  // Memory to be deleted (for confirmation)
}

func (m model) Init() tea.Cmd {
	return m.loadMemories()
}

func (m model) loadMemories() tea.Cmd {
	return tea.Cmd(func() tea.Msg {
		memories, err := m.api.GetAllMemories()
		if err != nil {
			return errMsg{err}
		}
		return memoriesLoadedMsg{memories}
	})
}

type memoriesLoadedMsg struct{ memories []Memory }
type memoryAddedMsg struct{}
type memoryDeletedMsg struct{}
type searchResultsMsg struct{ memories []Memory }
type errMsg struct{ error }

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd

	switch msg := msg.(type) {
	case tea.KeyMsg:
		if m.loading {
			return m, nil
		}

		// Handle global Tab navigation
		if msg.String() == "tab" {
			if m.focus == focusContent {
				m.focus = focusPrompt
				m.promptInput.Focus()
			} else {
				m.focus = focusContent
				m.promptInput.Blur()
			}
			return m, nil
		}

		// Handle prompt commands when focused
		if m.focus == focusPrompt {
			switch msg.String() {
			case "enter":
				return m.handlePromptCommand()
			case "esc":
				m.focus = focusContent
				m.promptInput.Blur()
				return m, nil
			default:
				m.promptInput, cmd = m.promptInput.Update(msg)
				return m, cmd
			}
		}

		// Handle content area updates when focused
		switch m.state {
		case listView:
			return m.updateListView(msg)
		case detailView:
			return m.updateDetailView(msg)
		case addView:
			return m.updateAddView(msg)
		case searchView:
			return m.updateSearchView(msg)
		case confirmDeleteView:
			return m.updateConfirmDeleteView(msg)
		}

	case memoriesLoadedMsg:
		m.loading = false
		m.memories = msg.memories
		items := make([]list.Item, len(msg.memories))
		for i, mem := range msg.memories {
			items[i] = memoryItem{memory: mem}
		}
		m.list.SetItems(items)
		m.message = fmt.Sprintf("Loaded %d memories", len(msg.memories))
		return m, nil

	case memoryAddedMsg:
		m.loading = false
		m.state = listView
		m.message = "Memory added successfully"
		return m, m.loadMemories()

	case memoryDeletedMsg:
		m.loading = false
		m.message = "Memory deleted successfully"
		return m, m.loadMemories()

	case searchResultsMsg:
		m.loading = false
		items := make([]list.Item, len(msg.memories))
		for i, mem := range msg.memories {
			items[i] = memoryItem{memory: mem}
		}
		m.list.SetItems(items)
		m.message = fmt.Sprintf("Found %d memories", len(msg.memories))
		return m, nil

	case errMsg:
		m.loading = false
		m.err = msg.error
		return m, nil

	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		m.list.SetWidth(msg.Width - 8) // Adjust for box padding and borders
		m.list.SetHeight(msg.Height - 8) // Leave space for prompt box
		m.textArea.SetWidth(msg.Width - 8) // Adjust for box padding and borders
		m.searchInput.Width = msg.Width - 20 // Adjust for box padding and "Command: " text
		m.promptInput.Width = msg.Width - 20 // Adjust for box padding and "Command: " text
		return m, nil
	}

	// Update the active component
	switch m.state {
	case listView:
		m.list, cmd = m.list.Update(msg)
	case addView:
		m.textArea, cmd = m.textArea.Update(msg)
	case searchView:
		m.searchInput, cmd = m.searchInput.Update(msg)
	case confirmDeleteView:
		// No component to update in confirmation view
	}

	return m, cmd
}

// Handle prompt commands
func (m model) handlePromptCommand() (tea.Model, tea.Cmd) {
	command := strings.TrimSpace(m.promptInput.Value())
	m.promptInput.SetValue("")

	if command == "" {
		return m, nil
	}

	// Split command and arguments
	parts := strings.SplitN(command, " ", 2)
	cmd := parts[0]
	var args string
	if len(parts) > 1 {
		args = strings.TrimSpace(parts[1])
	}

	switch cmd {
	case "/quit", "/q":
		return m, tea.Quit
	case "/add", "/a":
		if args == "" {
			m.message = "Usage: /add YOUR_MEMORY_TEXT"
			return m, nil
		}
		m.loading = true
		m.focus = focusContent
		m.promptInput.Blur()
		return m, tea.Cmd(func() tea.Msg {
			err := m.api.AddMemory(args, nil)
			if err != nil {
				return errMsg{err}
			}
			return memoryAddedMsg{}
		})
	case "/search", "/s":
		if args == "" {
			m.message = "Usage: /search YOUR_SEARCH_QUERY"
			return m, nil
		}
		m.loading = true
		m.focus = focusContent
		m.promptInput.Blur()
		return m, tea.Cmd(func() tea.Msg {
			results, err := m.api.SearchMemories(args, 20)
			if err != nil {
				return errMsg{err}
			}
			return searchResultsMsg{results}
		})
	case "/refresh", "/r":
		m.loading = true
		m.message = "Refreshing..."
		m.focus = focusContent
		m.promptInput.Blur()
		return m, m.loadMemories()
	default:
		m.message = fmt.Sprintf("Unknown command: %s. Available: /quit /add TEXT /search QUERY /refresh", cmd)
		return m, nil
	}
}

func (m model) updateListView(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch msg.String() {
	case "q", "ctrl+c":
		return m, tea.Quit
	case "enter":
		if len(m.memories) > 0 {
			selected := m.list.SelectedItem().(memoryItem)
			m.currentMem = selected.memory
			m.state = detailView
		}
		return m, nil
	case "delete", "backspace":
		if len(m.memories) > 0 {
			selected := m.list.SelectedItem().(memoryItem)
			m.memToDelete = selected.memory
			m.state = confirmDeleteView
		}
		return m, nil
	}

	var cmd tea.Cmd
	m.list, cmd = m.list.Update(msg)
	return m, cmd
}

func (m model) updateDetailView(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch msg.String() {
	case "q", "esc":
		m.state = listView
		return m, nil
	}
	return m, nil
}

func (m model) updateAddView(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch msg.String() {
	case "ctrl+s":
		if strings.TrimSpace(m.textArea.Value()) != "" {
			m.loading = true
			text := m.textArea.Value()
			return m, tea.Cmd(func() tea.Msg {
				err := m.api.AddMemory(text, nil)
				if err != nil {
					return errMsg{err}
				}
				return memoryAddedMsg{}
			})
		}
		return m, nil
	case "esc":
		m.state = listView
		return m, nil
	}

	var cmd tea.Cmd
	m.textArea, cmd = m.textArea.Update(msg)
	return m, cmd
}

func (m model) updateSearchView(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch msg.String() {
	case "enter":
		if strings.TrimSpace(m.searchInput.Value()) != "" {
			m.loading = true
			query := m.searchInput.Value()
			return m, tea.Cmd(func() tea.Msg {
				results, err := m.api.SearchMemories(query, 20)
				if err != nil {
					return errMsg{err}
				}
				return searchResultsMsg{results}
			})
		}
		return m, nil
	case "esc":
		m.state = listView
		return m, nil
	}

	var cmd tea.Cmd
	m.searchInput, cmd = m.searchInput.Update(msg)
	return m, cmd
}

func (m model) updateConfirmDeleteView(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	switch msg.String() {
	case "y", "Y":
		m.loading = true
		m.state = listView
		return m, tea.Cmd(func() tea.Msg {
			err := m.api.DeleteMemory(m.memToDelete.ID)
			if err != nil {
				return errMsg{err}
			}
			return memoryDeletedMsg{}
		})
	case "n", "N", "esc":
		m.state = listView
		return m, nil
	}
	return m, nil
}

func (m model) View() string {
	if m.loading {
		return "\n  Loading...\n\n"
	}

	var content string

	switch m.state {
	case listView:
		content = m.renderListView()
	case detailView:
		content = m.renderDetailModal()
	case addView:
		content = m.renderAddView()
	case searchView:
		content = m.renderSearchView()
	case confirmDeleteView:
		content = m.renderConfirmDeleteModal()
	}

	// Add status messages
	statusBar := ""
	if m.err != nil {
		statusBar = fmt.Sprintf("❌ Error: %v", m.err)
		m.err = nil // Clear error after showing
	} else if m.message != "" {
		statusBar = fmt.Sprintf("✅ %s", m.message)
		m.message = "" // Clear message after showing
	}

	// For modal states, don't show prompt box
	if m.state == detailView || m.state == confirmDeleteView {
		if statusBar != "" {
			return content + "\n\n" + statusBar
		}
		return content
	}

	// Render prompt box for non-modal states
	promptBox := m.renderPromptBox()

	// Combine content with prompt box at bottom
	if statusBar != "" {
		return content + "\n" + statusBar + "\n\n" + promptBox
	}
	return content + "\n\n" + promptBox
}

func (m model) renderPromptBox() string {
	var style lipgloss.Style
	if m.focus == focusPrompt {
		style = promptBoxFocusedStyle.Width(m.width - 4) // Full width minus small margins
	} else {
		style = promptBoxStyle.Width(m.width - 4) // Full width minus small margins
	}

	promptText := m.promptInput.View()
	if promptText == "" && m.focus != focusPrompt {
		promptText = "Press Tab to focus, then type: /quit /add TEXT /search QUERY /refresh"
	}

	return style.Render("Command: " + promptText)
}

func (m model) renderListView() string {
	var style lipgloss.Style
	if m.focus == focusContent {
		style = contentBoxFocusedStyle.Width(m.width - 4) // Full width minus small margins
	} else {
		style = contentBoxStyle.Width(m.width - 4) // Full width minus small margins
	}

	title := titleStyle.Render("🧠 Tom Memory Manager")
	help := helpStyle.Render("📝 Memory Manager | Tab: switch focus | Enter: view detail | Del: delete")
	listContent := fmt.Sprintf("%s\n%s\n%s", title, m.list.View(), help)
	
	return style.Render(listContent)
}

func (m model) renderDetailModal() string {
	modalWidth := min(80, m.width-10) // Max 80 chars wide, but leave margin
	
	var b strings.Builder
	b.WriteString(titleStyle.Render("📖 Memory Details"))
	b.WriteString("\n\n")
	
	b.WriteString(selectedItemStyle.Render("ID: "))
	b.WriteString(m.currentMem.ID)
	b.WriteString("\n\n")
	
	b.WriteString(selectedItemStyle.Render("Content:"))
	b.WriteString("\n")
	// Wrap content to fit modal width
	memoryContent := m.currentMem.Memory
	if len(memoryContent) > modalWidth-6 {
		b.WriteString(wrapText(memoryContent, modalWidth-6))
	} else {
		b.WriteString(memoryContent)
	}
	b.WriteString("\n\n")
	
	b.WriteString(selectedItemStyle.Render("Created: "))
	b.WriteString(formatTime(m.currentMem.CreatedAt))
	b.WriteString("\n")
	
	b.WriteString(selectedItemStyle.Render("Updated: "))
	if m.currentMem.UpdatedAt != nil {
		b.WriteString(formatTime(*m.currentMem.UpdatedAt))
	} else {
		b.WriteString("Never")
	}
	b.WriteString("\n")
	
	b.WriteString(selectedItemStyle.Render("User: "))
	b.WriteString(m.currentMem.UserID)
	b.WriteString("\n")
	
	b.WriteString(selectedItemStyle.Render("Hash: "))
	b.WriteString(truncateString(m.currentMem.Hash, 16))
	b.WriteString("\n\n")
	
	if len(m.currentMem.Metadata) > 0 {
		b.WriteString(selectedItemStyle.Render("Metadata:"))
		b.WriteString("\n")
		for k, v := range m.currentMem.Metadata {
			b.WriteString(fmt.Sprintf("  %s: %v\n", k, v))
		}
		b.WriteString("\n")
	}
	
	b.WriteString(helpStyle.Render("Esc: close"))
	
	// Center the modal content
	modalContent := modalStyle.Width(modalWidth).Render(b.String())
	return lipgloss.Place(m.width, m.height, lipgloss.Center, lipgloss.Center, modalContent)
}

// Helper function to wrap text
func wrapText(text string, width int) string {
	if len(text) <= width {
		return text
	}
	
	var result strings.Builder
	words := strings.Fields(text)
	currentLine := ""
	
	for _, word := range words {
		if len(currentLine)+len(word)+1 <= width {
			if currentLine != "" {
				currentLine += " "
			}
			currentLine += word
		} else {
			if currentLine != "" {
				result.WriteString(currentLine + "\n")
			}
			currentLine = word
		}
	}
	
	if currentLine != "" {
		result.WriteString(currentLine)
	}
	
	return result.String()
}

// Helper function for min
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func (m model) renderAddView() string {
	var style lipgloss.Style
	if m.focus == focusContent {
		style = contentBoxFocusedStyle.Width(m.width - 4) // Full width minus small margins
	} else {
		style = contentBoxStyle.Width(m.width - 4) // Full width minus small margins
	}

	var b strings.Builder
	b.WriteString(titleStyle.Render("➕ Add New Memory"))
	b.WriteString("\n\n")
	b.WriteString("Enter your memory content:\n\n")
	b.WriteString(m.textArea.View())
	b.WriteString("\n\n")
	b.WriteString(helpStyle.Render("Tab: switch focus | Ctrl+S: save | Esc: cancel"))
	return style.Render(b.String())
}

func (m model) renderSearchView() string {
	var style lipgloss.Style
	if m.focus == focusContent {
		style = contentBoxFocusedStyle.Width(m.width - 4) // Full width minus small margins
	} else {
		style = contentBoxStyle.Width(m.width - 4) // Full width minus small margins
	}

	var b strings.Builder
	b.WriteString(titleStyle.Render("🔍 Search Memories"))
	b.WriteString("\n\n")
	b.WriteString("Enter search query:\n\n")
	b.WriteString(m.searchInput.View())
	b.WriteString("\n\n")
	b.WriteString(helpStyle.Render("Tab: switch focus | Enter: search | Esc: cancel"))
	return style.Render(b.String())
}

func (m model) renderConfirmDeleteModal() string {
	modalWidth := min(60, m.width-10) // Max 60 chars wide, but leave margin

	var b strings.Builder
	b.WriteString(titleStyle.Render("⚠️ Confirm Delete"))
	b.WriteString("\n\n")
	b.WriteString("Are you sure you want to delete this memory?\n\n")
	
	b.WriteString(selectedItemStyle.Render("Memory: "))
	// Wrap memory content to fit modal
	memoryText := m.memToDelete.Memory
	if len(memoryText) > modalWidth-10 {
		b.WriteString(wrapText(memoryText, modalWidth-10))
	} else {
		b.WriteString(memoryText)
	}
	b.WriteString("\n\n")
	
	b.WriteString(selectedItemStyle.Render("ID: "))
	b.WriteString(truncateString(m.memToDelete.ID, 20))
	b.WriteString("\n\n")
	
	b.WriteString("This action cannot be undone.\n\n")
	b.WriteString(helpStyle.Render("Y: delete | N: cancel | Esc: cancel"))
	
	// Center the modal content
	modalContent := modalStyle.Width(modalWidth).Render(b.String())
	return lipgloss.Place(m.width, m.height, lipgloss.Center, lipgloss.Center, modalContent)
}

func main() {
	// Get API base URL from command line argument (required)
	if len(os.Args) < 2 {
		fmt.Println("Usage: memory-tui <API_BASE_URL>")
		fmt.Println("Example: memory-tui http://localhost:8080")
		os.Exit(1)
	}
	
	baseURL := os.Args[1]
	
	// Allow environment variable override
	if envURL := os.Getenv("MEMORY_API_URL"); envURL != "" {
		baseURL = envURL
	}

	api := NewMemoryAPI(baseURL)

	// Create list
	items := []list.Item{}
	delegate := list.NewDefaultDelegate()
	delegate.Styles.SelectedTitle = selectedItemStyle
	delegate.Styles.SelectedDesc = selectedItemStyle

	memoryList := list.New(items, delegate, 80, 20)
	memoryList.Title = "Memories"
	memoryList.SetShowStatusBar(false)

	// Create text input for search
	searchInput := textinput.New()
	searchInput.Placeholder = "Enter search query..."
	searchInput.Width = 50 // Will be adjusted on window resize

	// Create textarea for adding memories
	textArea := textarea.New()
	textArea.Placeholder = "Enter your memory content here..."
	textArea.SetWidth(80) // Will be adjusted on window resize
	textArea.SetHeight(10)

	// Create prompt input
	promptInput := textinput.New()
	promptInput.Placeholder = "/quit /add TEXT /search QUERY /refresh"
	promptInput.Width = 50 // Will be adjusted on window resize

	// Create model
	m := model{
		api:         api,
		state:       listView,
		focus:       focusContent,
		list:        memoryList,
		searchInput: searchInput,
		textArea:    textArea,
		promptInput: promptInput,
		loading:     true,
	}

	// Start the program
	p := tea.NewProgram(m, tea.WithAltScreen())
	if _, err := p.Run(); err != nil {
		log.Fatalf("Error running program: %v", err)
	}
}