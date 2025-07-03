package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"os/exec"
	"regexp"
	"strings"

	"github.com/charmbracelet/bubbles/textinput"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

// Styles
var (
	styleLoginBox = lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(lipgloss.Color("63")).
		Padding(1, 2)

	styleChatBox = lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(lipgloss.Color("63")).
		Padding(0, 1) // Add horizontal padding

	styleUserMessage = lipgloss.NewStyle().
		Foreground(lipgloss.Color("229"))

	styleBotMessage = lipgloss.NewStyle().
		Foreground(lipgloss.Color("86"))

	styleCommandBar = lipgloss.NewStyle().
		Foreground(lipgloss.Color("240")).
		Padding(0, 1)
)

type (
	loginSuccessMsg   struct{}
	resetSuccessMsg   struct{}
	notifMsg          string
	serverResponseMsg string
	errorMsg          struct{ error }
	serverResponse    struct {
		Response string `json:"response"`
	}
	tasksResponse struct {
		Message string `json:"message"`
		ID      int    `json:"id"`
	}
)

const (
	viewLogin = iota
	viewChat
)

type model struct {
	currentView   int
	usernameInput textinput.Model
	passwordInput textinput.Model
	viewport      viewport.Model
	chatInput     textinput.Model
	messages      []string
	client        *http.Client
	err           error
	width, height int
}

func initialModel() model {
	jar, _ := cookiejar.New(nil)
	client := &http.Client{Jar: jar}

	username := textinput.New()
	username.Placeholder = "Username"
	username.Focus()

	password := textinput.New()
	password.Placeholder = "Password"
	password.EchoMode = textinput.EchoPassword

	chat := textinput.New()
	chat.Placeholder = "Send a message or type a command..."

	return model{
		currentView:   viewLogin,
		usernameInput: username,
		passwordInput: password,
		chatInput:     chat,
		client:        client,
	}
}

func (m model) Init() tea.Cmd {
	return textinput.Blink
}

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	if m.err != nil {
		if _, ok := msg.(tea.KeyMsg); ok {
			return m, tea.Quit
		}
	}

	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		headerHeight := lipgloss.Height(m.headerView())
		footerHeight := lipgloss.Height(m.footerView())
		commandBarHeight := lipgloss.Height(m.commandBarView())
		verticalMarginHeight := headerHeight + footerHeight + commandBarHeight

		if m.currentView == viewChat {
			m.viewport.Width = m.width
			m.viewport.Height = m.height - verticalMarginHeight
			m.viewport.YPosition = headerHeight
			m.viewport.SetContent(m.renderMessages())
		}

	case tea.KeyMsg:
		switch msg.Type {
		case tea.KeyCtrlC:
			return m, tea.Quit
		case tea.KeyEnter:
			if m.currentView == viewLogin {
				return m, login(m)
			} else {
				userInput := m.chatInput.Value()
				m.chatInput.Reset()

				if strings.HasPrefix(userInput, "/") {
					return m.handleCommand(userInput)
				}

				m.messages = append(m.messages, "You: "+userInput)
				m.viewport.SetContent(m.renderMessages())
				m.viewport.GotoBottom()
				return m, sendMessage(m, userInput)
			}
		case tea.KeyTab:
			if m.currentView == viewLogin {
				if m.usernameInput.Focused() {
					m.usernameInput.Blur()
					m.passwordInput.Focus()
				} else {
					m.passwordInput.Blur()
					m.usernameInput.Focus()
				}
			}
		}
	case loginSuccessMsg:
		m.currentView = viewChat
		m.chatInput.Focus()
		headerHeight := lipgloss.Height(m.headerView())
		footerHeight := lipgloss.Height(m.footerView())
		commandBarHeight := lipgloss.Height(m.commandBarView())
		verticalMarginHeight := headerHeight + footerHeight + commandBarHeight
		m.viewport = viewport.New(m.width, m.height-verticalMarginHeight)
		m.viewport.YPosition = headerHeight
		m.messages = []string{"Tom: Welcome! Type /help for a list of commands."}
		m.viewport.SetContent(m.renderMessages())
		return m, textinput.Blink

	case serverResponseMsg:
		m.messages = append(m.messages, "Tom: "+string(msg))
		m.viewport.SetContent(m.renderMessages())
		m.viewport.GotoBottom()
		return m, nil

	case resetSuccessMsg:
		m.messages = []string{"Chat history has been reset."}
		m.viewport.SetContent(m.renderMessages())
		return m, nil

	case notifMsg:
		if string(msg) == "" {
			m.messages = append(m.messages, "System: No new notifications.")
		} else {
			m.messages = append(m.messages, "Notification: "+string(msg))
		}
		m.viewport.SetContent(m.renderMessages())
		m.viewport.GotoBottom()
		return m, nil

	case errorMsg:
		m.err = msg
		return m, nil
	}

	var cmd tea.Cmd
	var cmds []tea.Cmd
	if m.currentView == viewLogin {
		m.usernameInput, cmd = m.usernameInput.Update(msg)
		cmds = append(cmds, cmd)
		m.passwordInput, cmd = m.passwordInput.Update(msg)
		cmds = append(cmds, cmd)
	} else {
		m.viewport, cmd = m.viewport.Update(msg)
		cmds = append(cmds, cmd)
		m.chatInput, cmd = m.chatInput.Update(msg)
		cmds = append(cmds, cmd)
	}
	return m, tea.Batch(cmds...)
}

func (m *model) handleCommand(cmd string) (tea.Model, tea.Cmd) {
	switch cmd {
	case "/quit", "/exit":
		return m, tea.Quit
	case "/reset":
		return m, resetCmd(*m)
	case "/notif":
		return m, fetchNotifsCmd(*m)
	case "/help":
		m.messages = append(m.messages, "Available commands: /quit, /reset, /notif, /help")
		m.viewport.SetContent(m.renderMessages())
		m.viewport.GotoBottom()
		return m, nil
	default:
		m.messages = append(m.messages, fmt.Sprintf("Unknown command: %s", cmd))
		m.viewport.SetContent(m.renderMessages())
		m.viewport.GotoBottom()
		return m, nil
	}
}

func (m model) renderMessages() string {
	// Render messages with word wrap
	var renderedMessages []string
	// Correct width for message content, accounting for viewport padding/borders
	contentWidth := m.viewport.Width - styleChatBox.GetHorizontalFrameSize()
	for _, msg := range m.messages {
		style := styleBotMessage
		if strings.HasPrefix(msg, "You: ") {
			style = styleUserMessage
		}
		renderedMessages = append(renderedMessages, style.Copy().Width(contentWidth).Render(msg))
	}
	return strings.Join(renderedMessages, "\n")
}

func (m model) View() string {
	if m.err != nil {
		return fmt.Sprintf("\nError: %v\n\nPress any key to quit.", m.err)
	}

	if m.currentView == viewLogin {
		var b strings.Builder
		b.WriteString("Login to Tom TUI\n\n")
		b.WriteString(m.usernameInput.View())
		b.WriteString("\n")
		b.WriteString(m.passwordInput.View())
		b.WriteString("\n\n(tab to switch, enter to login)")
		ui := styleLoginBox.Render(b.String())
		return lipgloss.Place(m.width, m.height, lipgloss.Center, lipgloss.Center, ui)
	}

	return lipgloss.JoinVertical(lipgloss.Left, m.headerView(), m.viewport.View(), m.footerView(), m.commandBarView())
}

func (m model) headerView() string {
	title := styleChatBox.Render("Tom TUI")
	line := strings.Repeat("─", m.width-lipgloss.Width(title))
	return lipgloss.JoinHorizontal(lipgloss.Center, title, line)
}

func (m model) footerView() string {
	return styleChatBox.Copy().Width(m.width - 3).Render(m.chatInput.View())
}

func (m model) commandBarView() string {
	return styleCommandBar.Copy().Width(m.width).Render("Commands: /quit, /reset, /notif, /help")
}

func login(m model) tea.Cmd {
	return func() tea.Msg {
		resp, err := m.client.PostForm("http://localhost:8082/login", url.Values{
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

		return loginSuccessMsg{}
	}
}

func sendMessage(m model, userInput string) tea.Cmd {
	return func() tea.Msg {
		postBody, _ := json.Marshal(map[string]interface{}{
			"request": userInput,
			"lang":    "fr",
			"tts":     true, // Pretend we have TTS to prevent server-side generation
      "client_type": "tui",
		})

		req, err := http.NewRequest("POST", "http://localhost:8082/process", bytes.NewBuffer(postBody))
		if err != nil {
			return errorMsg{err}
		}
		req.Header.Set("Content-Type", "application/json")

		resp, err := m.client.Do(req)
		if err != nil {
			return errorMsg{err}
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			return errorMsg{fmt.Errorf("failed to send message: %s", resp.Status)}
		}

		body, err := io.ReadAll(resp.Body)
		if err != nil {
			return errorMsg{err}
		}

		var serverResp serverResponse
		if err := json.Unmarshal(body, &serverResp); err != nil {
			return errorMsg{err}
		}

		// Check for [open:URL] command
		re := regexp.MustCompile(`\[open:(\S+)\]`)
		matches := re.FindStringSubmatch(serverResp.Response)
		if len(matches) > 1 {
			urlToOpen := matches[1]
			cmd := exec.Command("firefox", urlToOpen)
			cmd.Start() // Run in background
		}

		// Clean the response for display
		cleanedResponse := re.ReplaceAllString(serverResp.Response, "")

		return serverResponseMsg(cleanedResponse)
	}
}

func resetCmd(m model) tea.Cmd {
	return func() tea.Msg {
		req, err := http.NewRequest("POST", "http://localhost:8082/reset", nil)
		if err != nil {
			return errorMsg{err}
		}

		resp, err := m.client.Do(req)
		if err != nil {
			return errorMsg{err}
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			return errorMsg{fmt.Errorf("reset failed: %s", resp.Status)}
		}

		return resetSuccessMsg{}
	}
}

func fetchNotifsCmd(m model) tea.Cmd {
	return func() tea.Msg {
		req, err := http.NewRequest("GET", "http://localhost:8082/tasks", nil)
		if err != nil {
			return errorMsg{err}
		}

		resp, err := m.client.Do(req)
		if err != nil {
			return errorMsg{err}
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			return errorMsg{fmt.Errorf("failed to fetch notifications: %s", resp.Status)}
		}

		body, err := io.ReadAll(resp.Body)
		if err != nil {
			return errorMsg{err}
		}

		var taskData tasksResponse
		if err := json.Unmarshal(body, &taskData); err != nil {
			return errorMsg{err}
		}

		return notifMsg(taskData.Message)
	}
}

func main() {
	// Note: We're not using tea.WithMouseCellMotion() to allow for text selection.
	p := tea.NewProgram(initialModel(), tea.WithAltScreen())
	if _, err := p.Run(); err != nil {
		log.Fatal(err)
	}
}







