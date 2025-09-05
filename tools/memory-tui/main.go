package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/list"
	"github.com/charmbracelet/bubbles/spinner"
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

// Authentication types
type (
	loginSuccessMsg   struct{}
	disconnectMsg     struct{}
	autoLoginMsg      struct{ username, password, serverURL, sessionCookie string; useSession bool }
	errorMsg          struct{ error }
)

type credentials struct {
	Username      string `json:"username"`
	Password      string `json:"password"`
	ServerURL     string `json:"server_url"`
	SessionCookie string `json:"session_cookie"`
}

// API Client
type MemoryAPI struct {
	ServerURL string // Tom server URL (e.g., https://tom.example.com)
	Client    *http.Client
}

func NewMemoryAPI(serverURL string) *MemoryAPI {
	jar, _ := cookiejar.New(nil)
	return &MemoryAPI{
		ServerURL: serverURL,
		Client: &http.Client{
			Jar:     jar,
			Timeout: 30 * time.Second,
		},
	}
}

func NewMemoryAPIWithClient(serverURL string, client *http.Client) *MemoryAPI {
	return &MemoryAPI{
		ServerURL: serverURL,
		Client:    client,
	}
}

// buildURL constructs the full URL for memory API endpoints
func (api *MemoryAPI) buildURL(endpoint string) string {
	// Always use /memory as the base path on the Tom server
	return api.ServerURL + "/memory" + endpoint
}

func (api *MemoryAPI) GetAllMemories() ([]Memory, error) {
	resp, err := api.Client.Get(api.buildURL("/memories"))
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
	resp, err := api.Client.Get(api.buildURL("/memory/" + id))
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

	resp, err := api.Client.Post(api.buildURL("/add"), "application/json", bytes.NewBuffer(jsonData))
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

	resp, err := api.Client.Post(api.buildURL("/search"), "application/json", bytes.NewBuffer(jsonData))
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
	req, err := http.NewRequest("DELETE", api.buildURL("/delete/"+id), nil)
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

	// Auth styles
	loginBoxStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(lipgloss.Color("63")).
			Padding(1, 2)

	promptBoxStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(lipgloss.Color("#626262")).
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
	connectingView viewState = iota
	loginView
	listView
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
	// Authentication fields
	spinner         spinner.Model
	usernameInput   textinput.Model
	passwordInput   textinput.Model
	serverInput     textinput.Model
	client          *http.Client
	serverURL       string
	
	// Original memory app fields
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
	return tea.Batch(m.spinner.Tick, checkAuth)
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

	// Handle authentication messages
	switch msg := msg.(type) {
	case autoLoginMsg:
		if msg.username != "" && msg.serverURL != "" {
			m.usernameInput.SetValue(msg.username)
			m.passwordInput.SetValue(msg.password)
			m.serverInput.SetValue(msg.serverURL)
			m.serverURL = msg.serverURL
			
			if msg.useSession && msg.sessionCookie != "" {
				// Use session cookie for authentication
				return m, sessionLogin(m, msg.sessionCookie)
			} else {
				// Use username/password for authentication
				return m, login(m)
			}
		} else {
			m.state = loginView
			return m, nil
		}

	case loginSuccessMsg:
		m.err = nil
		m.state = listView
		m.serverURL = m.serverInput.Value()
		
		// Initialize API client with the authenticated server URL and reuse the auth client
		m.api = NewMemoryAPIWithClient(m.serverURL, m.client)
		
		m.loading = true
		return m, m.loadMemories()

	case disconnectMsg:
		m.state = loginView
		m.usernameInput.Reset()
		m.passwordInput.Reset()
		m.serverInput.Reset()
		m.memories = nil
		m.usernameInput.Focus()
		return m, nil

	case errorMsg:
		m.err = msg
		if m.state == connectingView {
			return m, tea.Batch(m.spinner.Tick, func() tea.Msg {
				time.Sleep(3 * time.Second)
				return checkAuth()
			})
		}
		return m, nil
	}

	switch msg := msg.(type) {
	case tea.KeyMsg:
		// Handle authentication views
		if m.state == connectingView {
			if msg.Type == tea.KeyCtrlC {
				return m, tea.Quit
			}
			return m, nil
		}
		
		if m.state == loginView {
			switch msg.Type {
			case tea.KeyCtrlC:
				return m, tea.Quit
			case tea.KeyEnter:
				m.state = connectingView
				m.serverInput.SetValue(strings.TrimSuffix(m.serverInput.Value(), "/"))
				return m, tea.Batch(m.spinner.Tick, login(m))
			case tea.KeyTab:
				if m.usernameInput.Focused() {
					m.usernameInput.Blur()
					m.passwordInput.Focus()
				} else if m.passwordInput.Focused() {
					m.passwordInput.Blur()
					m.serverInput.Focus()
				} else {
					m.serverInput.Blur()
					m.usernameInput.Focus()
				}
			}
			
			// Update auth inputs
			m.usernameInput, cmd = m.usernameInput.Update(msg)
			cmds := []tea.Cmd{cmd}
			m.passwordInput, cmd = m.passwordInput.Update(msg)
			cmds = append(cmds, cmd)
			m.serverInput, cmd = m.serverInput.Update(msg)
			cmds = append(cmds, cmd)
			
			return m, tea.Batch(cmds...)
		}

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
		// Force complete list recreation to ensure clean display
		m.list.SetItems([]list.Item{}) // Clear first
		m.list.SetItems(items)         // Then set new items
		m.list.ResetSelected()         // Reset selection
		m.message = fmt.Sprintf("Loaded %d memories", len(msg.memories))
		// Force a complete screen redraw
		return m, tea.ClearScreen

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
		// Force complete list recreation to ensure clean display
		m.list.SetItems([]list.Item{}) // Clear first
		m.list.SetItems(items)         // Then set new items
		m.list.ResetSelected()         // Reset selection
		m.message = fmt.Sprintf("Found %d memories", len(msg.memories))
		// Force a complete screen redraw
		return m, tea.ClearScreen

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
		// Force a refresh of the list display when window size changes
		if m.state == listView {
			m.list.ResetSelected()
		}
		return m, nil

	case spinner.TickMsg:
		if m.state == connectingView {
			m.spinner, cmd = m.spinner.Update(msg)
			return m, cmd
		}
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
	case "/disconnect", "/logout":
		return m, disconnect
	default:
		m.message = fmt.Sprintf("Unknown command: %s. Available: /quit /add TEXT /search QUERY /refresh /disconnect", cmd)
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
	// Handle authentication views first
	if m.err != nil && (m.state == connectingView || m.state == loginView) {
		return fmt.Sprintf("\nError: %v\n\nPress Ctrl+C to quit.\n", m.err)
	}

	if m.state == connectingView {
		var s strings.Builder
		s.WriteString(m.spinner.View())
		s.WriteString(" Connecting to server...")
		if m.err != nil {
			s.WriteString("\n\nConnection failed. Retrying...")
		}
		ui := loginBoxStyle.Render(s.String())
		return lipgloss.Place(m.width, m.height, lipgloss.Center, lipgloss.Center, ui)
	}

	if m.state == loginView {
		var b strings.Builder
		b.WriteString("Memory Manager Login\n\n")
		b.WriteString(m.usernameInput.View())
		b.WriteString("\n")
		b.WriteString(m.passwordInput.View())
		b.WriteString("\n")
		b.WriteString(m.serverInput.View())
		b.WriteString("\n\n(tab to switch, enter to login)")
		ui := loginBoxStyle.Render(b.String())
		return lipgloss.Place(m.width, m.height, lipgloss.Center, lipgloss.Center, ui)
	}

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
		promptText = "Press Tab to focus, then type: /quit /add TEXT /search QUERY /refresh /disconnect"
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
	
	// Get the list view
	listView := m.list.View()
	
	// Calculate the exact dimensions for the list display area
	availableHeight := m.list.Height()
	availableWidth := m.list.Width()
	
	// Split the current list view into lines
	listLines := strings.Split(listView, "\n")
	
	// If we have fewer lines than available height, fill the rest with blank lines
	if len(listLines) < availableHeight {
		blankLines := clearListArea(availableHeight-len(listLines), availableWidth)
		listLines = append(listLines, blankLines...)
	}
	
	// If we have more lines than available height, truncate
	if len(listLines) > availableHeight {
		listLines = listLines[:availableHeight]
	}
	
	// Ensure each line is exactly the right width (pad or truncate)
	for i, line := range listLines {
		if len(line) < availableWidth {
			listLines[i] = line + strings.Repeat(" ", availableWidth-len(line))
		} else if len(line) > availableWidth {
			listLines[i] = line[:availableWidth]
		}
	}
	
	// Join back into a single string
	paddedListView := strings.Join(listLines, "\n")
	
	listContent := fmt.Sprintf("%s\n%s\n%s", title, paddedListView, help)
	
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

// Helper function to create a blank line of specified width
func createBlankLine(width int) string {
	if width <= 0 {
		return ""
	}
	return strings.Repeat(" ", width)
}

// Helper function to clear the list display area completely
func clearListArea(height, width int) []string {
	lines := make([]string, height)
	for i := range lines {
		lines[i] = createBlankLine(width)
	}
	return lines
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

// Authentication functions
func getAuthFilePath() (string, error) {
	usr, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(usr, ".tom", "auth"), nil
}

func saveCredentials(username, password, serverURL, sessionCookie string) error {
	authPath, err := getAuthFilePath()
	if err != nil {
		return err
	}

	if err := os.MkdirAll(filepath.Dir(authPath), 0700); err != nil {
		return err
	}

	creds := credentials{
		Username:      username,
		Password:      password,
		ServerURL:     serverURL,
		SessionCookie: sessionCookie,
	}

	data, err := json.Marshal(creds)
	if err != nil {
		return err
	}

	encodedData := base64.StdEncoding.EncodeToString(data)

	return os.WriteFile(authPath, []byte(encodedData), 0600)
}

func loadCredentials() (string, string, string, string, error) {
	authPath, err := getAuthFilePath()
	if err != nil {
		return "", "", "", "", err
	}

	encodedData, err := os.ReadFile(authPath)
	if err != nil {
		return "", "", "", "", err
	}

	decodedData, err := base64.StdEncoding.DecodeString(string(encodedData))
	if err != nil {
		return "", "", "", "", err	
	}

	var creds credentials
	if err := json.Unmarshal(decodedData, &creds); err != nil {
		return "", "", "", "", err
	}

	return creds.Username, creds.Password, creds.ServerURL, creds.SessionCookie, nil
}

func deleteCredentials() error {
	authPath, err := getAuthFilePath()
	if err != nil {
		return err
	}
	return os.Remove(authPath)
}

func validateSessionCookie(serverURL, sessionCookie string, client *http.Client) bool {
	if sessionCookie == "" {
		return false
	}
	
	// Create a test request to verify the session cookie - use a simple endpoint
	req, err := http.NewRequest("GET", serverURL+"/status", nil)
	if err != nil {
		return false
	}
	
	// Set the session cookie
	req.Header.Set("Cookie", sessionCookie)
	
	resp, err := client.Do(req)
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	
	// If we get a 200 response, the session is valid
	return resp.StatusCode == http.StatusOK
}

func checkAuth() tea.Msg {
	username, password, serverURL, sessionCookie, err := loadCredentials()
	if err != nil {
		return autoLoginMsg{} // No credentials, stay on login view
	}
	
	// Create a temporary client to test the session cookie
	jar, _ := cookiejar.New(nil)
	client := &http.Client{
		Jar:     jar,
		Timeout: 30 * time.Second,
	}
	
	// First, try to use the session cookie if it exists
	if sessionCookie != "" && validateSessionCookie(serverURL, sessionCookie, client) {
		return autoLoginMsg{username, password, serverURL, sessionCookie, true}
	}
	
	// If session cookie is invalid or doesn't exist, use username/password
	return autoLoginMsg{username, password, serverURL, sessionCookie, false}
}

func disconnect() tea.Msg {
	if err := deleteCredentials(); err != nil {
		return errorMsg{fmt.Errorf("failed to disconnect: %w", err)}
	}
	return disconnectMsg{}
}

func sessionLogin(m model, sessionCookie string) tea.Cmd {
	return func() tea.Msg {
		// Set the session cookie in the client
		if sessionCookie != "" {
			req, err := http.NewRequest("GET", m.serverURL+"/status", nil)
			if err != nil {
				return errorMsg{err}
			}
			req.Header.Set("Cookie", sessionCookie)
			
			// Test the session cookie
			resp, err := m.client.Do(req)
			if err != nil {
				return errorMsg{err}
			}
			defer resp.Body.Close()
			
			if resp.StatusCode == http.StatusOK {
				return loginSuccessMsg{}
			}
		}
		
		// If session cookie is invalid, fall back to username/password login
		return login(m)()
	}
}

func login(m model) tea.Cmd {
	return func() tea.Msg {
		serverURL := m.serverInput.Value()
		if serverURL == "" {
			return errorMsg{fmt.Errorf("server URL is required")}
		}

		resp, err := m.client.PostForm(serverURL+"/login", url.Values{
			"username": {m.usernameInput.Value()},
			"password": {m.passwordInput.Value()},
		})
		if err != nil {
			return errorMsg{err}
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			bodyBytes, _ := io.ReadAll(resp.Body)
			return errorMsg{fmt.Errorf("login failed: %s (%s)", resp.Status, string(bodyBytes))}
		}

		// Extract session cookie from response
		sessionCookie := ""
		for _, cookie := range resp.Cookies() {
			if cookie.Name == "session_id" {
				sessionCookie = cookie.String()
				break
			}
		}

		if err := saveCredentials(m.usernameInput.Value(), m.passwordInput.Value(), serverURL, sessionCookie); err != nil {
			return errorMsg{fmt.Errorf("failed to save credentials: %w", err)}
		}

		return loginSuccessMsg{}
	}
}

func initialModel() model {
	jar, _ := cookiejar.New(nil)
	client := &http.Client{
		Jar:     jar,
		Timeout: 5 * time.Minute,
	}

	// Auth inputs
	username := textinput.New()
	username.Placeholder = "Username"
	username.Focus()
	username.Width = 20

	password := textinput.New()
	password.Placeholder = "Password"
	password.EchoMode = textinput.EchoPassword
	password.Width = 20

	server := textinput.New()
	server.Placeholder = "Server URL"
	server.Width = 40

	// Memory app inputs
	searchInput := textinput.New()
	searchInput.Placeholder = "Enter search query..."
	searchInput.Width = 50

	textArea := textarea.New()
	textArea.Placeholder = "Enter your memory content here..."
	textArea.SetWidth(80)
	textArea.SetHeight(10)

	promptInput := textinput.New()
	promptInput.Placeholder = "/quit /add TEXT /search QUERY /refresh /disconnect"
	promptInput.Width = 50

	// Create list
	items := []list.Item{}
	delegate := list.NewDefaultDelegate()
	delegate.Styles.SelectedTitle = selectedItemStyle
	delegate.Styles.SelectedDesc = selectedItemStyle

	memoryList := list.New(items, delegate, 80, 20)
	memoryList.Title = "Memories"
	memoryList.SetShowStatusBar(false)

	s := spinner.New()
	s.Spinner = spinner.Dot
	s.Style = lipgloss.NewStyle().Foreground(lipgloss.Color("205"))

	return model{
		// Auth fields
		spinner:       s,
		usernameInput: username,
		passwordInput: password,
		serverInput:   server,
		client:        client,
		
		// Memory app fields
		state:       connectingView,
		focus:       focusContent,
		list:        memoryList,
		searchInput: searchInput,
		textArea:    textArea,
		promptInput: promptInput,
		loading:     false,
	}
}

func main() {
	p := tea.NewProgram(initialModel(), tea.WithAltScreen())
	if _, err := p.Run(); err != nil {
		log.Fatal(err)
	}
}