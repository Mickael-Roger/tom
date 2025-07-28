package com.tom.assistant.ui.tasks

import android.graphics.Color
import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import com.tom.assistant.databinding.ItemTaskBinding
import com.tom.assistant.models.BackgroundTask

class TasksAdapter : RecyclerView.Adapter<TasksAdapter.TaskViewHolder>() {

    private val tasks = mutableListOf<BackgroundTask>()

    fun updateTasks(newTasks: List<BackgroundTask>) {
        tasks.clear()
        tasks.addAll(newTasks)
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): TaskViewHolder {
        val binding = ItemTaskBinding.inflate(
            LayoutInflater.from(parent.context),
            parent,
            false
        )
        return TaskViewHolder(binding)
    }

    override fun onBindViewHolder(holder: TaskViewHolder, position: Int) {
        holder.bind(tasks[position])
    }

    override fun getItemCount(): Int = tasks.size

    inner class TaskViewHolder(private val binding: ItemTaskBinding) :
        RecyclerView.ViewHolder(binding.root) {

        fun bind(task: BackgroundTask) {
            binding.tvModule.text = task.module
            binding.tvStatus.text = task.status

            // Changer la couleur du statut selon le type
            val statusColor = when (task.status.lowercase()) {
                "running", "active" -> Color.parseColor("#4CAF50") // Vert
                "error", "failed" -> Color.parseColor("#F44336") // Rouge
                "waiting", "pending" -> Color.parseColor("#FF9800") // Orange
                else -> Color.parseColor("#2196F3") // Bleu par défaut
            }
            
            binding.tvStatus.setTextColor(Color.WHITE)
            binding.tvStatus.setBackgroundColor(statusColor)
        }
    }
}