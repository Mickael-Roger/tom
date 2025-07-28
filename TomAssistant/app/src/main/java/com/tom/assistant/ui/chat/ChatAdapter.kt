package com.tom.assistant.ui.chat

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import com.tom.assistant.databinding.ItemChatMessageBinding
import com.tom.assistant.models.ChatMessage
import io.noties.markwon.Markwon

class ChatAdapter(private val markwon: Markwon) : RecyclerView.Adapter<ChatAdapter.ChatViewHolder>() {

    private val messages = mutableListOf<ChatMessage>()

    fun addMessage(message: ChatMessage) {
        messages.add(message)
        notifyItemInserted(messages.size - 1)
    }

    fun clearMessages() {
        messages.clear()
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ChatViewHolder {
        val binding = ItemChatMessageBinding.inflate(
            LayoutInflater.from(parent.context),
            parent,
            false
        )
        return ChatViewHolder(binding)
    }

    override fun onBindViewHolder(holder: ChatViewHolder, position: Int) {
        holder.bind(messages[position])
    }

    override fun getItemCount(): Int = messages.size

    inner class ChatViewHolder(private val binding: ItemChatMessageBinding) :
        RecyclerView.ViewHolder(binding.root) {

        fun bind(message: ChatMessage) {
            if (message.isFromUser) {
                // Message utilisateur
                binding.layoutUserMessage.visibility = View.VISIBLE
                binding.layoutBotMessage.visibility = View.GONE
                binding.tvUserMessage.text = message.content
            } else {
                // Message bot
                binding.layoutUserMessage.visibility = View.GONE
                binding.layoutBotMessage.visibility = View.VISIBLE
                
                // Traiter les commandes personnalisées comme [open:URL]
                val processedText = processCustomCommands(message.content)
                
                // Utiliser Markwon pour rendre le markdown
                markwon.setMarkdown(binding.tvBotMessage, processedText)
            }
        }
        
        private fun processCustomCommands(text: String): String {
            // Supprimer les commandes [open:URL] du texte affiché
            return text.replace(Regex("\\[open:.*?\\]"), "").trim()
        }
    }
}